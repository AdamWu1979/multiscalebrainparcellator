# Copyright (C) 2017-2019, Brain Communication Pathways Sinergia Consortium, Switzerland
# All rights reserved.
#
#  This software is distributed under the open-source license Modified BSD.

""" Anatomical pipeline Class definition
"""

# General imports
import datetime
import os
import glob
import fnmatch
import shutil
import threading
import multiprocessing
import time

# PyBIDS import
from bids import BIDSLayout

# Nipype util imports
import nipype.interfaces.io as nio
from nipype import config, logging
from nipype.utils.filemanip import copyfile
import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util

from nipype.caching import Memory
from nipype.interfaces.base import CommandLineInputSpec, CommandLine, traits, BaseInterface, \
    BaseInterfaceInputSpec, File, TraitedSpec, isdefined, Directory, InputMultiPath
from nipype.utils.filemanip import split_filename

# Nipype interfaces
from nipype.interfaces.dcm2nii import Dcm2niix
import nipype.interfaces.fsl as fsl
import nipype.interfaces.freesurfer as fs

# Traits
from traits.api import *

# Own import
import cmp.interfaces.fsl as cmp_fsl

import cmp.multiscalebrainparcellator.pipelines.common as cmp_common
from cmp.multiscalebrainparcellator.stages.segmentation.segmentation import SegmentationStage
from cmp.multiscalebrainparcellator.stages.parcellation.parcellation import ParcellationStage

from cmtklib.util import bcolors

class Global_Configuration(HasTraits):
    process_type = Str('anatomical')
    subjects = List(trait=Str)
    subject = Str
    subject_session = Str

# class Check_Input_Notification(HasTraits):
#     message = Str
#     diffusion_imaging_model_options = List(['DSI','DTI','HARDI'])
#     diffusion_imaging_model = Str
#     diffusion_imaging_model_message = Str('\nMultiple diffusion inputs available. Please select desired diffusion modality.')
#
#     traits_view = View(Item('message',style='readonly',show_label=False),
#                        Item('diffusion_imaging_model_message',visible_when='len(diffusion_imaging_model_options)>1',style='readonly',show_label=False),
#                        Item('diffusion_imaging_model',editor=EnumEditor(name='diffusion_imaging_model_options'),visible_when='len(diffusion_imaging_model_options)>1'),
#                        kind='modal',
#                        buttons=['OK'],
#                        title="Check inputs")

class AnatomicalPipeline(cmp_common.Pipeline):
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    pipeline_name = Str("anatomical_pipeline")
    input_folders = ['anat']
    process_type = Str
    diffusion_imaging_model = Str
    parcellation_scheme = Str('Lausanne2008')
    atlas_info = Dict()

    #subject = Str
    subject_directory = Directory
    #derivatives_directory = Directory

    global_conf = Global_Configuration()
    config_file = Str

    flow = Instance(pe.Workflow)

    def __init__(self,project_info):
        self.stages = {'Segmentation':SegmentationStage(),
            'Parcellation':ParcellationStage()}

        cmp_common.Pipeline.__init__(self, project_info)
        #super(Pipeline, self).__init__(project_info)

        self.subject = project_info.subject
        self.last_date_processed = project_info.anat_last_date_processed

        self.global_conf.subjects = project_info.subjects
        self.global_conf.subject = self.subject

        if len(project_info.subject_sessions) > 0:
            self.global_conf.subject_session = project_info.subject_session
            self.subject_directory =  os.path.join(self.base_directory,self.subject,self.global_conf.subject_session)
        else:
            self.global_conf.subject_session = ''
            self.subject_directory =  os.path.join(self.base_directory,self.subject)

        #self.derivatives_directory =  os.path.join(self.base_directory,'derivatives')
        self.output_directory =  project_info.output_directory

        self.stages['Segmentation'].config.on_trait_change(self.update_parcellation,'seg_tool')
        self.stages['Parcellation'].config.on_trait_change(self.update_segmentation,'parcellation_scheme')

        self.stages['Parcellation'].config.on_trait_change(self.update_parcellation_scheme,'parcellation_scheme')

    def check_config(self):
        # if self.stages['Segmentation'].config.seg_tool ==  'Custom segmentation':
        #     if not os.path.exists(self.stages['Segmentation'].config.white_matter_mask):
        #         return('\nCustom segmentation selected but no WM mask provided.\nPlease provide an existing WM mask file in the Segmentation configuration window.\n')
        #     if not os.path.exists(self.stages['Parcellation'].config.atlas_nifti_file):
        #         return('\n\tCustom segmentation selected but no atlas provided.\nPlease specify an existing atlas file in the Parcellation configuration window.\t\n')
        #     if not os.path.exists(self.stages['Parcellation'].config.graphml_file):
        #         return('\n\tCustom segmentation selected but no graphml info provided.\nPlease specify an existing graphml file in the Parcellation configuration window.\t\n')
        return ''

    def update_parcellation_scheme(self):
        self.parcellation_scheme = self.stages['Parcellation'].config.parcellation_scheme
        self.atlas_info = self.stages['Parcellation'].config.atlas_info

    def update_parcellation(self):
        if self.stages['Segmentation'].config.seg_tool == "Custom segmentation" :
            self.stages['Parcellation'].config.parcellation_scheme = 'Custom'
        else:
            self.stages['Parcellation'].config.parcellation_scheme = self.stages['Parcellation'].config.pre_custom

    def update_segmentation(self):
        if self.stages['Parcellation'].config.parcellation_scheme == 'Custom':
            self.stages['Segmentation'].config.seg_tool = "Custom segmentation"
        else:
            self.stages['Segmentation'].config.seg_tool = 'Freesurfer'

    def check_input(self, layout):
        print('**** Check Inputs  ****')
        t1_available = False
        t1_json_available = False
        valid_inputs = False

        print("  > Looking in %s for...." % self.base_directory)  

        types = layout.get_modalities()

        subjid = self.subject.split("-")[1]

        if self.global_conf.subject_session == '':
            T1_file = os.path.join(self.subject_directory,'anat',self.subject+'_T1w.nii.gz')
            files = layout.get(subject=subjid,suffix='T1w',extensions='.nii.gz')
            if len(files) > 0:
                T1_file = os.path.join(files[0].dirname,files[0].filename)
                print T1_file
            else:
                pass
        else:
            sessid = self.global_conf.subject_session.split("-")[1]
            files = layout.get(subject=subjid,suffix='T1w',extensions='.nii.gz',session=sessid)
            if len(files) > 0:
                T1_file = os.path.join(files[0].dirname,files[0].filename)
                print T1_file
            else:
                pass

        print("  ... t1_file : %s" % T1_file)

        if self.global_conf.subject_session == '':
            T1_json_file = os.path.join(self.subject_directory,'anat',self.subject+'_T1w.json')
            files = layout.get(subject=subjid,suffix='T1w',extensions='.json')
            if len(files) > 0:
                T1_json_file = os.path.join(files[0].dirname,files[0].filename)
                print T1_json_file
            else:
                pass
        else:
            sessid = self.global_conf.subject_session.split("-")[1]
            files = layout.get(subject=subjid,suffix='T1w',extensions='.json',session=sessid)
            if len(files) > 0:
                T1_json_file = os.path.join(files[0].dirname,files[0].filename)
                print T1_json_file
            else:
                pass

        print("  ... t1_json_file : %s" % T1_json_file)

        if os.access(T1_file,os.F_OK):
            # print("%s available" % typ)
            t1_available = True

        if os.access(T1_json_file,os.F_OK):
            # print("%s available" % typ)
            t1_json_available = True

        if t1_available:
            #Copy T1w data to derivatives / cmp  / subject / anat
            if self.global_conf.subject_session == '':
                out_T1_file = os.path.join(self.output_directory,'cmp',self.subject,'anat',self.subject+'_desc-cmp_T1w.nii.gz')
            else:
                out_T1_file = os.path.join(self.output_directory,'cmp',self.subject,self.global_conf.subject_session,'anat',self.subject+'_'+self.global_conf.subject_session+'_desc-cmp_T1w.nii.gz')

            if not os.path.isfile(out_T1_file):
                print('  * Copying {} to {}'.format(T1_file,out_T1_file))
                shutil.copy(src=T1_file,dst=out_T1_file)

            valid_inputs = True
            input_message = '  * Inputs check finished successfully. \n    Only anatomical data (T1) available.'

            if t1_json_available:
                if self.global_conf.subject_session == '':
                    out_T1_json_file = os.path.join(self.output_directory,'cmp',self.subject,'anat',self.subject+'_desc-cmp_T1w.json')
                else:
                    out_T1_json_file = os.path.join(self.output_directory,'cmp',self.subject,self.global_conf.subject_session,'anat',self.subject+'_'+self.global_conf.subject_session+'_desc-cmp_T1w.json')

                if not os.path.isfile(out_T1_json_file):
                    print('  * Copying {} to {}'.format(T1_json_file,out_T1_json_file))
                    shutil.copy(src=T1_json_file,dst=out_T1_json_file)

        else:
            if self.global_conf.subject_session == '':
                input_message = bcolors.FAIL + '  * Error during inputs check. No anatomical data available in folder '+os.path.join(self.base_directory,self.subject)+'/anat/!' + bcolors.ENDC
            else:
                input_message = bcolors.FAIL + '  * Error during inputs check. No anatomical data available in folder '+os.path.join(self.base_directory,self.subject,self.global_conf.subject_session)+'/anat/!' + bcolors.ENDC

        print(input_message)

        if(t1_available):
            valid_inputs = True
        else:
            print(bcolors.FAIL + '  * Error : Missing required inputs. Please see documentation for more details.' + bcolors.ENDC)

        if not t1_json_available:
            print(bcolors.WARNING + '  * Warning : Missing BIDS json sidecar. Please see documentation for more details.' + bcolors.ENDC)

        # for stage in self.stages.values():
        #     if stage.enabled:
        #         print stage.name
        #         print stage.stage_dir

        #self.fill_stages_outputs()

        return valid_inputs

    def check_output(self):
        print('**** Check Outputs  ****')
        t1_available = False
        brain_available = False
        brainmask_available = False
        wm_available = False
        roivs_available = False
        valid_output = False

        subject = self.subject

        if self.global_conf.subject_session == '':
            anat_deriv_subject_directory = os.path.join(self.output_directory,"cmp",self.subject,'anat')
        else:
            if self.global_conf.subject_session not in subject:
                anat_deriv_subject_directory = os.path.join(self.output_directory,"cmp",subject,self.global_conf.subject_session,'anat')
                subject = "_".join((subject,self.global_conf.subject_session))
            else:
                anat_deriv_subject_directory = os.path.join(self.output_directory,"cmp",subject.split("_")[0],self.global_conf.subject_session,'anat')

        T1_file = os.path.join(anat_deriv_subject_directory,subject+'_desc-head_T1w.nii.gz')
        brain_file = os.path.join(anat_deriv_subject_directory,subject+'_desc-brain_T1w.nii.gz')
        brainmask_file = os.path.join(anat_deriv_subject_directory,subject+'_desc-brainmask_dseg.nii.gz')
        wm_mask_file = os.path.join(anat_deriv_subject_directory,subject+'_label-WM_dseg.nii.gz')
        roiv_files = glob.glob(anat_deriv_subject_directory+"/"+subject+"_label-L2018_desc-scale*_atlas.nii.gz")

        error_message = ''

        if os.path.isfile(T1_file):
            t1_available = True
        else:
            error_message = bcolors.FAIL+"  * Missing anatomical output file %s . Please re-run the anatomical pipeline".format(T1_file) + bcolors.ENDC
            print error_message
            
        if os.path.isfile(brain_file):
            brain_available = True
        else:
            error_message = bcolors.FAIL+"  * Missing anatomical output file %s . Please re-run the anatomical pipeline".format(brain_file) + bcolors.ENDC
            print error_message
            
        if os.path.isfile(brainmask_file):
            brainmask_available = True
        else:
            error_message = bcolors.FAIL+"  * Missing anatomical output file %s . Please re-run the anatomical pipeline".format(brainmask_file) + bcolors.ENDC
            print error_message
            
        if os.path.isfile(wm_mask_file):
            wm_available = True
        else:
            error_message = bcolors.FAIL+"  * Missing anatomical output file %s . Please re-run the anatomical pipeline".format(wm_mask_file) + bcolors.ENDC
            print error_message
            
        cnt1=0
        cnt2=0
        for roiv_file in roiv_files:
            cnt1 = cnt1 + 1
            if os.path.isfile(roiv_file): cnt2 = cnt2 + 1
        if cnt1 == cnt2:
            roivs_available = True
        else:
            error_message = bcolors.FAIL+"  * Missing %g/%g anatomical parcellation output files. Please re-run the anatomical pipeline".format(cnt1-cnt2,cnt1) + bcolors.ENDC
            print error_message
            
        if t1_available == True and brain_available == True and brainmask_available == True and wm_available == True and roivs_available == True:
            print(" * Valid outputs")
            valid_output = True

        return valid_output,error_message

    def create_pipeline_flow(self,deriv_subject_directory,nipype_deriv_subject_directory):
        print('**** Create pipeline flow  ****')
        subject_directory = self.subject_directory

        # Data import
        datasource = pe.Node(interface=nio.DataGrabber(outfields = ['T1']), name='datasource')
        datasource.inputs.base_directory = deriv_subject_directory
        datasource.inputs.template = '*'
        datasource.inputs.raise_on_empty = False
        datasource.inputs.field_template = dict(T1='anat/'+self.subject+'_desc-cmp_T1w.nii.gz')
        datasource.inputs.sort_filelist=False

        # Data sinker for output
        sinker = pe.Node(nio.DataSink(), name="anatomical_sinker")
        sinker.inputs.base_directory = os.path.join(deriv_subject_directory)

        #Dataname substitutions in order to comply with BIDS derivatives specifications
        if self.stages['Segmentation'].config.seg_tool == "Freesurfer":
            sinker.inputs.substitutions = [ ('T1.nii.gz', self.subject+'_desc-head_T1w.nii.gz'),
                                            ('brain.nii.gz', self.subject+'_desc-brain_T1w.nii.gz'),
                                            ('brain_mask.nii.gz', self.subject+'_desc-brain_mask.nii.gz'),
                                            ('aseg.nii.gz', self.subject+'_desc-aseg_dseg.nii.gz'),
                                            ('fsmask_1mm.nii.gz',self.subject+'_label-WM_dseg.nii.gz'),
                                            #('gmmask.nii.gz',self.subject+'_label-GM_dseg.nii.gz'),
                                            ('T1w_class-GM.nii.gz',self.subject+'_label-GM_dseg.nii.gz'),
                                            ('aparc+aseg.native.nii.gz',self.subject+'_desc-aparcaseg_dseg.nii.gz'),
                                            ('aparc+aseg.Lausanne2018.native.nii.gz',self.subject+'_desc-aparcaseg_dseg.nii.gz'),
                                            ('roi_stats_scale1.tsv',self.subject+'_label-L2018_desc-scale1_stats.tsv'),
                                            ('roi_stats_scale2.tsv',self.subject+'_label-L2018_desc-scale2_stats.tsv'),
                                            ('roi_stats_scale3.tsv',self.subject+'_label-L2018_desc-scale3_stats.tsv'),
                                            ('roi_stats_scale4.tsv',self.subject+'_label-L2018_desc-scale4_stats.tsv'),
                                            ('roi_stats_scale5.tsv',self.subject+'_label-L2018_desc-scale5_stats.tsv'),
                                            ('ROIv_HR_th_scale1.nii.gz',self.subject+'_label-L2018_desc-scale1_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale2.nii.gz',self.subject+'_label-L2018_desc-scale2_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale3.nii.gz',self.subject+'_label-L2018_desc-scale3_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale4.nii.gz',self.subject+'_label-L2018_desc-scale4_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale5.nii.gz',self.subject+'_label-L2018_desc-scale5_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale1_final.nii.gz',self.subject+'_label-L2018_desc-scale1_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale2_final.nii.gz',self.subject+'_label-L2018_desc-scale2_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale3_final.nii.gz',self.subject+'_label-L2018_desc-scale3_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale4_final.nii.gz',self.subject+'_label-L2018_desc-scale4_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale5_final.nii.gz',self.subject+'_label-L2018_desc-scale5_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale1.graphml',self.subject+'_label-L2018_desc-scale1_atlas.graphml'),
                                            ('ROIv_HR_th_scale2.graphml',self.subject+'_label-L2018_desc-scale2_atlas.graphml'),
                                            ('ROIv_HR_th_scale3.graphml',self.subject+'_label-L2018_desc-scale3_atlas.graphml'),
                                            ('ROIv_HR_th_scale4.graphml',self.subject+'_label-L2018_desc-scale4_atlas.graphml'),
                                            ('ROIv_HR_th_scale5.graphml',self.subject+'_label-L2018_desc-scale5_atlas.graphml'),
                                            ('ROIv_HR_th_scale1_FreeSurferColorLUT.txt',self.subject+'_label-L2018_desc-scale1_atlas_FreeSurferColorLUT.txt'),
                                            ('ROIv_HR_th_scale2_FreeSurferColorLUT.txt',self.subject+'_label-L2018_desc-scale2_atlas_FreeSurferColorLUT.txt'),
                                            ('ROIv_HR_th_scale3_FreeSurferColorLUT.txt',self.subject+'_label-L2018_desc-scale3_atlas_FreeSurferColorLUT.txt'),
                                            ('ROIv_HR_th_scale4_FreeSurferColorLUT.txt',self.subject+'_label-L2018_desc-scale4_atlas_FreeSurferColorLUT.txt'),
                                            ('ROIv_HR_th_scale5_FreeSurferColorLUT.txt',self.subject+'_label-L2018_desc-scale5_atlas_FreeSurferColorLUT.txt'),
                                            ('ROIv_HR_th_scale33.nii.gz',self.subject+'_label-L2018_desc-scale1_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale60.nii.gz',self.subject+'_label-L2018_desc-scale2_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale125.nii.gz',self.subject+'_label-L2018_desc-scale3_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale250.nii.gz',self.subject+'_label-L2018_desc-scale4_atlas.nii.gz'),
                                            ('ROIv_HR_th_scale500.nii.gz',self.subject+'_label-L2018_desc-scale5_atlas.nii.gz'),
                                          ]
        else:
            sinker.inputs.substitutions = [ (self.subject+'_T1w.nii.gz', self.subject+'_T1w_head.nii.gz'),
                                            ('brain_mask.nii.gz', self.subject+'_T1w_brainmask.nii.gz'),
                                            ('brainmask_eroded.nii.gz', self.subject+'_T1w_brainmask_eroded.nii.gz'),
                                            ('brain.nii.gz', self.subject+'_T1w_brain.nii.gz'),
                                            ('fsmask_1mm.nii.gz',self.subject+'_T1w_class-WM.nii.gz'),
                                            ('fsmask_1mm_eroded.nii.gz',self.subject+'_T1w_class-WM_eroded.nii.gz'),
                                            ('csf_mask_eroded.nii.gz',self.subject+'_T1w_class-CSF_eroded.nii.gz'),
                                            #('gm_mask',self.subject+'_T1w_class-GM'),
                                            #('roivs', self.subject+'_T1w_parc'),#TODO substitute for list of files
                                            ('T1w_class-GM.nii.gz',self.subject+'_T1w_class-GM.nii.gz'),
                                            ('ROIv_HR_th_scale1.nii.gz',self.subject+'_T1w_parc_scale1.nii.gz'),
                                            ('ROIv_HR_th_scale2.nii.gz',self.subject+'_T1w_parc_scale2.nii.gz'),
                                            ('ROIv_HR_th_scale3.nii.gz',self.subject+'_T1w_parc_scale3.nii.gz'),
                                            ('ROIv_HR_th_scale4.nii.gz',self.subject+'_T1w_parc_scale4.nii.gz'),
                                            ('ROIv_HR_th_scale5.nii.gz',self.subject+'_T1w_parc_scale5.nii.gz'),
                                            ('ROIv_HR_th_scale33.nii.gz',self.subject+'_T1w_parc_scale1.nii.gz'),
                                            ('ROIv_HR_th_scale60.nii.gz',self.subject+'_T1w_parc_scale2.nii.gz'),
                                            ('ROIv_HR_th_scale125.nii.gz',self.subject+'_T1w_parc_scale3.nii.gz'),
                                            ('ROIv_HR_th_scale250.nii.gz',self.subject+'_T1w_parc_scale4.nii.gz'),
                                            ('ROIv_HR_th_scale500.nii.gz',self.subject+'_T1w_parc_scale5.nii.gz'),
                                          ]

        # Create common_flow
        anat_flow = pe.Workflow(name='anatomical_pipeline', base_dir=nipype_deriv_subject_directory)
        anat_inputnode = pe.Node(interface=util.IdentityInterface(fields=["T1"]),name="inputnode")
        anat_outputnode = pe.Node(interface=util.IdentityInterface(fields=["subjects_dir","subject_id","T1","aseg","aparc_aseg","brain","brain_mask","wm_mask_file", "gm_mask_file", "wm_eroded","brain_eroded","csf_eroded",
            "roi_volumes","roi_volumes_stats","parcellation_scheme","atlas_info","roi_colorLUTs", "roi_graphMLs"]),name="outputnode")
        
        anat_flow.add_nodes([anat_inputnode,anat_outputnode])

        anat_flow.connect([
                        (datasource,anat_inputnode,[("T1","T1")]),
                        ])

        if self.stages['Segmentation'].enabled:
            if self.stages['Segmentation'].config.seg_tool == "Freesurfer":
                self.stages['Segmentation'].config.freesurfer_subjects_dir = os.path.join(self.output_directory,'freesurfer')
                print "Freesurfer_subjects_dir: %s" % self.stages['Segmentation'].config.freesurfer_subjects_dir
                self.stages['Segmentation'].config.freesurfer_subject_id = os.path.join(self.output_directory,'freesurfer',self.subject)
                print "Freesurfer_subject_id: %s" % self.stages['Segmentation'].config.freesurfer_subject_id

            seg_flow = self.create_stage_flow("Segmentation")

            anat_flow.connect([(anat_inputnode,seg_flow, [('T1','inputnode.T1')])])

            anat_flow.connect([
                        (seg_flow,anat_outputnode,[("outputnode.subjects_dir","subjects_dir"),
                                                     ("outputnode.subject_id","subject_id")])
                        ])

        if self.stages['Parcellation'].enabled:
            parc_flow = self.create_stage_flow("Parcellation")
            if self.stages['Segmentation'].config.seg_tool == "Freesurfer":
                anat_flow.connect([(seg_flow,parc_flow, [('outputnode.subjects_dir','inputnode.subjects_dir'),
                                                           ('outputnode.subject_id','inputnode.subject_id')]),
                                     ])

                anat_flow.connect([
                                    (parc_flow,anat_outputnode,[("outputnode.wm_mask_file","wm_mask_file"),
                                                               ("outputnode.parcellation_scheme","parcellation_scheme"),
                                                               ("outputnode.atlas_info","atlas_info"),
                                                               ("outputnode.roi_volumes","roi_volumes"),
                                                               ("outputnode.roi_colorLUTs","roi_colorLUTs"),
                                                               ("outputnode.roi_graphMLs","roi_graphMLs"),
                                                               ("outputnode.roi_volumes_stats","roi_volumes_stats"),
                                                               ("outputnode.wm_eroded","wm_eroded"),
                                                               ("outputnode.gm_mask_file","gm_mask_file"),
                                                               ("outputnode.csf_eroded","csf_eroded"),
                                                               ("outputnode.brain_eroded","brain_eroded"),
                                                               ("outputnode.T1","T1"),
                                                               ("outputnode.aseg","aseg"),
                                                               ("outputnode.aparc_aseg","aparc_aseg"),
                                                               ("outputnode.brain_mask","brain_mask"),
                                                               ("outputnode.brain","brain"),
                                                               ])
                                ])

        anat_flow.connect([
                        (anat_outputnode,sinker,[("T1","anat.@T1")]),
                        (anat_outputnode,sinker,[("aseg","anat.@aseg")]),
                        (anat_outputnode,sinker,[("aparc_aseg","anat.@aparc_aseg")]),
                        (anat_outputnode,sinker,[("brain","anat.@brain")]),
                        (anat_outputnode,sinker,[("brain_mask","anat.@brain_mask")]),
                        (anat_outputnode,sinker,[("wm_mask_file","anat.@wm_mask")]),
                        (anat_outputnode,sinker,[("gm_mask_file","anat.@gm_mask")]),
                        (anat_outputnode,sinker,[("roi_volumes","anat.@roivs")]),
                        (anat_outputnode,sinker,[("roi_colorLUTs","anat.@luts")]),
                        (anat_outputnode,sinker,[("roi_graphMLs","anat.@graphmls")]),
                        (anat_outputnode,sinker,[("roi_volumes_stats","anat.@stats")]),
                        ])

        self.flow = anat_flow
        return anat_flow



    def process(self):
        # Process time
        self.now = datetime.datetime.now().strftime("%Y%m%d_%H%M")

        if '_' in self.subject:
            self.subject = self.subject.split('_')[0]

        old_subject = self.subject

        if self.global_conf.subject_session == '':
            deriv_subject_directory = os.path.join(self.output_directory,"cmp",self.subject)
            nipype_deriv_subject_directory = os.path.join(self.output_directory,"nipype",self.subject)
        else:
            deriv_subject_directory = os.path.join(self.output_directory,"cmp",self.subject,self.global_conf.subject_session)
            nipype_deriv_subject_directory = os.path.join(self.output_directory,"nipype",self.subject,self.global_conf.subject_session)

            self.subject = "_".join((self.subject,self.global_conf.subject_session))

        # Initialization
        if os.path.isfile(os.path.join(deriv_subject_directory,"anat","{}_desc-multiscalbrainparcellator_log.txt".format(self.subject))):
            os.unlink(os.path.join(deriv_subject_directory,"anat","{}_desc-multiscalbrainparcellator_log.txt".format(self.subject)))

        config.update_config({'logging': {'log_directory': os.path.join(deriv_subject_directory,"anat"),
                                  'log_to_file': True},
                              'execution': {'remove_unnecessary_outputs': False,
                              'stop_on_first_crash': True,'stop_on_first_rerun': False,
                              'crashfile_format': "txt"}
                              })
        logging.update_logging(config)
        iflogger = logging.getLogger('nipype.interface')

        anat_flow = self.create_pipeline_flow(deriv_subject_directory=deriv_subject_directory, nipype_deriv_subject_directory=nipype_deriv_subject_directory)
        anat_flow.write_graph(graph2use='colored', format='svg', simple_form=True)

        iflogger.info("**** Processing ****")
        
        if(self.number_of_cores != 1):
            print("  * Number of cores used: {}".format(self.number_of_cores))
            #print(os.environ)
            anat_flow.run(plugin='MultiProc', plugin_args={'n_procs' : self.number_of_cores})
        else:
            print("  * Number of cores used: {}".format(self.number_of_cores))
            #print(os.environ)
            anat_flow.run()

        # Clean undesired folders/files
        # rm_file_list = ['rh.EC_average','lh.EC_average','fsaverage']
        # for file_to_rm in rm_file_list:
        #     if os.path.exists(os.path.join(self.base_directory,file_to_rm)):
        #         os.remove(os.path.join(self.base_directory,file_to_rm))

        # copy .ini and log file
        # outdir = deriv_subject_directory
        # if not os.path.exists(outdir):
        #     os.makedirs(outdir)

        # try:
        #     src = os.path.join(deriv_subject_directory,"anat","pypeline.log")
        #     dest = os.path.join(deriv_subject_directory,"anat", "{}_desc-multiscalebrainparcellator_log.txt".format(self.subject))
        #     shutil.move(src,dest)
        # except:
        #     print("Skipped renaming of log file")

        # try:
        #     shutil.copy(self.config_file,outdir)
        # except shutil.Error:
        #     print("Skipped copy of config file")

        #shutil.copy(os.path.join(self.output_directory,"cmp",self.subject,'pypeline.log'),outdir)

        iflogger.info("**** Processing finished ****")

        return True,'Processing successful'
