## Multi-Scale Brain Parcellator
The Multi-Scale Brain Parcellator is a BIDS App that implements a full anatomical MRI processing pipeline using FreeSurfer 6.0.1 and the Connectome Mapping Toolkit, from raw T1w data to structural brain parcellation at five different scales.

![Image not found](images/multiscalebrainparcellator.png)


[//]: # (### Documentation)

[//]: <> (More information and documentation can be found at [https://connectome-mapper-3.readthedocs.io](https://connectome-mapper-3.readthedocs.io))

### License
This software is distributed under the open-source license Modified BSD. See [license](LICENSE) for more details.

### Usage
This App has the following command line arguments:

        $ docker -ti --rm sebastientourbier/multiscalebrainparcellator --help

        usage: multiscalebrainparcellator_bidsapp_entrypointscript [-h]
                                        [--participant_label PARTICIPANT_LABEL [PARTICIPANT_LABEL ...]]
                                        [--thalamic_nuclei]
                                        [--hippocampal_subfields]
                                        [--brainstem_structures]
                                        [-v]
                                        bids_dir output_dir {participant,group}

        Multi-scale Brain Parcellator BIDS App entrypoint script.

        positional arguments:
          bids_dir              The directory with the input dataset formatted
                                according to the BIDS standard.
          output_dir            The directory where the output files should be stored.
                                If you are running group level analysis this folder
                                should be prepopulated with the results of
                                theparticipant level analysis.
          {participant,group}   Level of the analysis that will be performed. Multiple
                                participant level analyses can be run independently
                                (in parallel) using the same output_dir.

        optional arguments:
          -h, --help            show this help message and exit
          --participant_label PARTICIPANT_LABEL [PARTICIPANT_LABEL ...]
                                The label(s) of the participant(s) that should be
                                analyzed. The label corresponds to
                                sub-<participant_label> from the BIDS spec (so it does
                                not include "sub-"). If this parameter is not provided
                                all subjects should be analyzed. Multiple participants
                                can be specified with a space separated list.
          --thalamic_nuclei     Segment thalamic thalamic_nuclei
          --hippocampal_subfields Segment hippocampal subfields (FreeSurfer)
          --brainstem_structures Segment brainstem structures (FreeSurfer)
          -v, --version         show program's version number and exit

#### Participant level
To run it in participant level mode (for one participant):

        docker run -it --rm \
        -v /home/localadmin/data/ds001:/bids_dataset \
        -v /media/localadmin/data/ds001/derivatives:/bids_dataset/derivatives \
        -v /usr/local/freesurfer/license.txt:/opt/freesurfer/license.txt \
        sebastientourbier/multiscalebrainparcellator:latest \
        /bids_dataset /bids_dataset/derivatives participant --participant_label 01 \
        --thalamic_nuclei \
        --hippocampal_subfields \
        --brainstem_structures

#### Group level
To run it in group level mode (for one participant):
<!--TODO  -->

### Credits
* Patric Hagmann (pahagman)
* Sebastien Tourbier (sebastientourbier)
* Yasser Aleman (yasseraleman)

### Funding

Work supported by the [Sinergia SNF-170873 Grant](http://p3.snf.ch/Project-170873).

### Copyright
Copyright (C) 2009-2019, Brain Communication Pathways Sinergia Consortium, Switzerland.
