#!/usr/bin/env python
# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
NiBetaSeries processing workflows
"""
from __future__ import print_function, division, absolute_import, unicode_literals
import os
from copy import deepcopy

from bids import BIDSLayout
from nipype.pipeline import engine as pe
from nipype.interfaces import utility as niu
from niworkflows.engine.workflows import LiterateWorkflow as Workflow

from bids import __version__ as pybids_ver
from numpy import __version__ as numpy_ver
from pandas import __version__ as pandas_ver
from nipype import __version__ as nipype_ver
from nibabel import __version__ as nibabel_ver
from niworkflows import __version__ as niworkflows_ver

from .._version import get_versions
from .utils import collect_data, BIDSLayoutIndexerPatch
from .model import init_betaseries_wf
from .analysis import init_correlation_wf
from ..interfaces.bids import DerivativesDataSink
from ..interfaces.nilearn import CensorVolumes


def init_nibetaseries_participant_wf(
    estimator, atlas_img, atlas_lut, bids_dir,
    database_path, derivatives_pipeline_dir, exclude_description_label,
    fir_delays, hrf_model, high_pass, norm_betas, output_dir, return_residuals,
    run_label, selected_confounds, session_label, signal_scaling, smoothing_kernel,
    space_label, subject_list, task_label, description_label, work_dir,
        ):

    """
    This workflow organizes the execution of NiBetaSeries, with a sub-workflow for
    each subject.

    Parameters
    ----------

        atlas_img : str
            Path to input atlas nifti
        atlas_lut : str
            Path to input atlas lookup table (tsv)
        bids_dir : str
            Root directory of BIDS dataset
        database_path : str
            Path to a BIDS database
        derivatives_pipeline_dir : str
            Root directory of the derivatives pipeline
        exclude_description_label : str or None
            Exclude bold series containing this description label
        fir_delays : list or None
            FIR delays (in scans)
        hrf_model : str
            The model that represents the shape of the hemodynamic response function
        high_pass : float
            High pass filter to apply to bold (in Hertz).
            Reminder - frequencies _higher_ than this number are kept.
        norm_betas : Bool
            If True, beta estimates are divided by the square root of their variance
        output_dir : str
            Directory where derivatives are saved
        return_residuals : bool
            Output the residuals from the betaseries model into the
            derivatives directory
        run_label : str or None
            Include bold series containing this run label
        selected_confounds : list
            List of confounds to be included in regression
        signal_scaling : False or 0
            Whether (0) or not (False) to scale each voxel's timeseries
        session_label : str or None
            Include bold series containing this session label
        smoothing_kernel : float or None
            The smoothing kernel to be applied to the bold series before beta estimation
        space_label : str or None
            Include bold series containing this space label
        subject_list : list
            List of subject labels
        task_label : str or None
            Include bold series containing this task label
        description_label : str or None
            Include bold series containing this description label
        work_dir : str
            Directory in which to store workflow execution state and temporary files
    """
    # setup workflow
    nibetaseries_participant_wf = Workflow(name='nibetaseries_participant_wf')
    nibetaseries_participant_wf.base_dir = os.path.join(work_dir, 'NiBetaSeries_work')
    os.makedirs(nibetaseries_participant_wf.base_dir, exist_ok=True)

    nibetaseries_participant_wf.__desc__ = """
Results included in this manuscript come from modeling
performed using *NiBetaSeries* {nibs_ver} [@Kent2018],
which is based on *Nipype* {nipype_ver} [@Gorgolewski2011; @Gorgolewski2018].
""".format(nibs_ver=get_versions()['version'],
           nipype_ver=nipype_ver)

    nibetaseries_participant_wf.__postdesc__ = """

### Software Dependencies

Additional libraries used in the NiBetaSeries workflow include
*Pybids* {pybids_ver} [@Yarkoni2019], *Niworkflows* {niworkflows_ver},
*Nibabel* {nibabel_ver}, *Pandas* {pandas_ver} [@McKinney2010], and
*Numpy* {numpy_ver} [@VanDerWalt2011; @Oliphant2006].

### Copyright Waiver
The above boilerplate text was automatically generated by NiBetaSeries
with the express intention that users should copy and paste this
text into their manuscripts *unchanged*.
It is released under the [CC0]\
(https://creativecommons.org/publicdomain/zero/1.0/) license.

### References
""".format(pybids_ver=pybids_ver,
           niworkflows_ver=niworkflows_ver,
           nibabel_ver=nibabel_ver,
           pandas_ver=pandas_ver,
           numpy_ver=numpy_ver)

    # Go ahead and initialize the layout database
    if database_path is None:
        database_path = os.path.join(work_dir, 'dbcache')
        reset_database = True
    else:
        reset_database = False

    # reading in derivatives and bids inputs as queryable database like objects
    layout = BIDSLayout(bids_dir,
                        derivatives=derivatives_pipeline_dir,
                        index_metadata=False,
                        database_file=database_path,
                        reset_database=reset_database)

    # only index bold file metadata
    if reset_database:
        indexer = BIDSLayoutIndexerPatch(layout)
        metadata_filter = {
            'extension': ['nii', 'nii.gz', 'json'],
            'suffix': 'bold',
        }
        indexer.index_metadata(**metadata_filter)

    for subject_label in subject_list:
        # collect the necessary inputs for both collect data
        subject_data = collect_data(layout,
                                    subject_label,
                                    task=task_label,
                                    run=run_label,
                                    ses=session_label,
                                    space=space_label,
                                    description=description_label)
        # collect files to be associated with each preproc
        brainmask_list = [d['brainmask'] for d in subject_data]
        confound_tsv_list = [d['confounds'] for d in subject_data]
        events_tsv_list = [d['events'] for d in subject_data]
        preproc_img_list = [d['preproc'] for d in subject_data]
        bold_metadata_list = [d['metadata'] for d in subject_data]

        single_subject_wf = init_single_subject_wf(
            estimator=estimator,
            atlas_img=atlas_img,
            atlas_lut=atlas_lut,
            bold_metadata_list=bold_metadata_list,
            brainmask_list=brainmask_list,
            confound_tsv_list=confound_tsv_list,
            events_tsv_list=events_tsv_list,
            fir_delays=fir_delays,
            hrf_model=hrf_model,
            high_pass=high_pass,
            name='single_subject' + subject_label + '_wf',
            norm_betas=norm_betas,
            output_dir=output_dir,
            preproc_img_list=preproc_img_list,
            return_residuals=return_residuals,
            selected_confounds=selected_confounds,
            signal_scaling=signal_scaling,
            smoothing_kernel=smoothing_kernel,
        )

        # add nibetaseries to the output directory because of DerivativesDataSink class
        single_subject_wf.config['execution']['crashdump_dir'] = (
            os.path.join(output_dir, "nibetaseries", "sub-" + subject_label, 'log')
        )

        for node in single_subject_wf._get_all_nodes():
            node.config = deepcopy(single_subject_wf.config)

        nibetaseries_participant_wf.add_nodes([single_subject_wf])

    return nibetaseries_participant_wf


def init_single_subject_wf(
    estimator, atlas_img, atlas_lut, bold_metadata_list, brainmask_list,
    confound_tsv_list, events_tsv_list, fir_delays, hrf_model, high_pass,
    name, norm_betas, output_dir, preproc_img_list, return_residuals,
    selected_confounds, signal_scaling, smoothing_kernel,
        ):
    """
    This workflow completes the generation of the betaseries files
    and the calculation of the correlation matrices.
    .. workflow::
        :graph2use: orig
        :simple_form: yes

        from nibetaseries.workflows.base import init_single_subject_wf
        wf = init_single_subject_wf(
            estimator='lss',
            atlas_img='',
            atlas_lut='',
            bold_metadata_list=[''],
            brainmask_list=[''],
            confound_tsv_list=[''],
            events_tsv_list=[''],
            fir_delays=None,
            hrf_model='',
            high_pass='',
            name='subtest',
            norm_betas=False,
            output_dir='.',
            preproc_img_list=[''],
            selected_confounds=[''],
            signal_scaling=0,
            smoothing_kernel=0.0)

    Parameters
    ----------

        atlas_img : str or None
            path to input atlas nifti
        atlas_lut : str or None
            path to input atlas lookup table (tsv)
        bold_metadata_list : list
            list of bold metadata associated with each preprocessed file
        brainmask_list : list
            list of brain masks
        confound_tsv_list : list
            list of confound tsvs (e.g. from FMRIPREP)
        events_tsv_list : list
            list of event tsvs
        fir_delays : list or None
            FIR delays (in scans)
        hrf_model : str
            hemodynamic response function used to model the data
        high_pass : float
            High pass filter to apply to bold (in Hertz).
            Reminder - frequencies _higher_ than this number are kept.
        norm_betas : Bool
            If True, beta estimates are divided by the square root of their variance
        name : str
            name of the workflow (e.g. ``subject-01_wf``)
        output_dir : str
            Directory where derivatives are saved
        preproc_img_list : list
            list of preprocessed bold files
        return_residuals : bool
            Output the residuals from the betaseries model into the
            derivatives directory
        selected_confounds : list or None
            the list of confounds to be included in regression
        signal_scaling : False or 0
            Whether (0) or not (False) to scale each voxel's timeseries
        smoothing_kernel : float or None
            the size of the smoothing kernel (full width/half max) applied to the bold file (in mm)

   Inputs
   ------

        atlas_img
            path to input atlas nifti
        atlas_lut
            path to input atlas lookup table (tsv)
        bold_metadata
            bold metadata associated with the preprocessed file
        brainmask
            binary mask for the participant
        confound_tsv
            tsv containing all the generated confounds
        events_tsv
            tsv containing all of the events that occurred during the bold run
        preproc_img
            preprocessed bold files

    Outputs
    -------

        correlation_matrix
            a matrix (tsv) file denoting all roi-roi correlations
        correlation_fig
            a svg file of a circular connectivity plot showing all roi-roi correlations
    """
    workflow = Workflow(name=name)

    # name the nodes
    input_node = pe.Node(niu.IdentityInterface(fields=['atlas_img',
                                                       'atlas_lut',
                                                       'bold_metadata',
                                                       'brainmask',
                                                       'confound_tsv',
                                                       'events_tsv',
                                                       'preproc_img',
                                                       ]),
                         name='input_node',
                         iterables=[('brainmask', brainmask_list),
                                    ('confound_tsv', confound_tsv_list),
                                    ('events_tsv', events_tsv_list),
                                    ('preproc_img', preproc_img_list),
                                    ('bold_metadata', bold_metadata_list)],
                         synchronize=True)

    output_node = pe.Node(niu.IdentityInterface(fields=['correlation_matrix',
                                                        'correlation_fig',
                                                        'betaseries_file',
                                                        'residual_file']),
                          name='output_node')

    # initialize the betaseries workflow
    betaseries_wf = init_betaseries_wf(estimator=estimator,
                                       fir_delays=fir_delays,
                                       hrf_model=hrf_model,
                                       high_pass=high_pass,
                                       norm_betas=norm_betas,
                                       selected_confounds=selected_confounds,
                                       signal_scaling=signal_scaling,
                                       smoothing_kernel=smoothing_kernel)

    # initialize the analysis workflow
    correlation_wf = init_correlation_wf()

    # correlation matrix datasink
    ds_correlation_matrix = pe.MapNode(DerivativesDataSink(base_directory=output_dir),
                                       iterfield=['in_file'],
                                       name='ds_correlation_matrix')

    ds_correlation_fig = pe.MapNode(DerivativesDataSink(base_directory=output_dir),
                                    iterfield=['in_file'],
                                    name='ds_correlation_fig')

    ds_betaseries_file = pe.MapNode(DerivativesDataSink(base_directory=output_dir),
                                    iterfield=['in_file'],
                                    name='ds_betaseries_file')

    # connect the nodes for the beta series workflow
    workflow.connect([
        (input_node, betaseries_wf,
            [('preproc_img', 'input_node.bold_file'),
             ('events_tsv', 'input_node.events_file'),
             ('brainmask', 'input_node.bold_mask_file'),
             ('confound_tsv', 'input_node.confounds_file'),
             ('bold_metadata', 'input_node.bold_metadata')]),
        (betaseries_wf, output_node,
            [('output_node.betaseries_files', 'betaseries_file')]),
        (input_node, ds_betaseries_file, [('preproc_img', 'source_file')]),
        (output_node, ds_betaseries_file, [('betaseries_file', 'in_file')]),
    ])

    if atlas_img and atlas_lut:
        # connect the nodes for the atlas workflow
        input_node.inputs.atlas_img = atlas_img
        input_node.inputs.atlas_lut = atlas_lut

        check_beta_series_list = pe.Node(niu.Function(
                                            function=_check_bs_len,
                                            output_names=["beta_series_list"]),
                                         name="check_beta_series_list")

        censor_volumes = pe.MapNode(CensorVolumes(),
                                    iterfield=['timeseries_file'],
                                    name='censor_volumes')

        workflow.connect([
            (input_node, censor_volumes,
                [('brainmask', 'mask_file')]),
            (betaseries_wf, censor_volumes,
                [('output_node.betaseries_files', 'timeseries_file')]),
            (censor_volumes, check_beta_series_list,
                [('censored_file', 'beta_series_list')]),
            (check_beta_series_list, correlation_wf,
                [('beta_series_list', 'input_node.betaseries_files')]),
            (input_node, correlation_wf,
                [('atlas_img', 'input_node.atlas_file'),
                 ('atlas_lut', 'input_node.atlas_lut')]),
            (correlation_wf, output_node,
                [('output_node.correlation_matrix', 'correlation_matrix'),
                 ('output_node.correlation_fig', 'correlation_fig')]),
            (input_node, ds_correlation_matrix, [('preproc_img', 'source_file')]),
            (output_node, ds_correlation_matrix, [('correlation_matrix', 'in_file')]),
            (input_node, ds_correlation_fig, [('preproc_img', 'source_file')]),
            (output_node, ds_correlation_fig, [('correlation_fig', 'in_file')]),
        ])

    if return_residuals:
        ds_residual_file = pe.MapNode(DerivativesDataSink(base_directory=output_dir),
                                      iterfield=['in_file'],
                                      name='ds_residual_file')

        workflow.connect([
            (betaseries_wf, output_node,
                [('output_node.residual_file', 'residual_file')]),
            (output_node, ds_residual_file,
                [('residual_file', 'in_file')]),
            (input_node, ds_residual_file,
                [('preproc_img', 'source_file')]),
        ])

    return workflow


def _check_bs_len(beta_series_list):
    """make sure each beta series at least 3 betas"""
    import logging
    import re

    import nibabel as nib

    min_size = 3

    def check_beta_series(beta_series, min_size):
        size = nib.load(beta_series).shape[-1]
        if size < min_size:
            mtch = re.match(".*desc-(?P<trial_type>[0-9A-Za-z]+)_.*", beta_series)
            if mtch:
                trial_type = mtch.groupdict().get('trial_type')
            else:
                trial_type = 'UNKNOWN'
                logging.warning(
                    "this file: {file} contains an unknown trial_type".format(file=beta_series))
            logging.warning(
                'At least {min_size} trials are needed '
                'for a beta series: {trial_type} has {num}'.format(
                    trial_type=trial_type,
                    num=size,
                    min_size=min_size))
            return False
        return True

    beta_series_list[:] = [bs for bs in beta_series_list
                           if check_beta_series(bs, min_size=min_size)]
    if not beta_series_list:
        msg = "None of the beta series have at least {num} betas.".format(num=min_size)
        raise RuntimeError(msg)

    return beta_series_list
