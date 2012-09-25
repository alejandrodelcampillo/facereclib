#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# Manuel Guenther <Manuel.Guenther@idiap.ch>


import sys, os
import argparse

from . import ToolChainExecutor
from .. import toolchain

class ToolChainExecutorGBU (ToolChainExecutor.ToolChainExecutor):

  def __init__(self, args, protocol):
    # call base class constructor
    ToolChainExecutor.ToolChainExecutor.__init__(self, args)

    # set (overwrite) the protocol
    self.m_configuration.protocol = protocol

    # specify the file selector and tool chain objects to be used by this class (and its base class)
    self.m_file_selector = toolchain.FileSelectorZT(self.m_configuration, self.m_configuration)
    self.m_tool_chain = toolchain.ToolChainZT(self.m_file_selector)


  def protocol_specific_configuration(self):
    """Special configuration for GBU protocol"""
    # set the dictionary for the options to assure that we use the 'gbu' protocol type
    self.m_configuration.__dict__['all_files_options'] = {'type' : 'gbu'}
    self.m_configuration.__dict__['extractor_training_options'] = {'type' : 'gbu'}
    self.m_configuration.__dict__['projector_training_options'] = {'type' : 'gbu'}
    self.m_configuration.__dict__['enroller_training_options'] = {'type' : 'gbu'}
    self.m_configuration.__dict__['models_options'] = {'type' : 'gbu'}

    self.m_configuration.models_dir = os.path.join(self.m_configuration.base_output_TEMP_dir, self.m_args.model_dir, self.m_configuration.protocol)
    self.m_configuration.scores_nonorm_dir = os.path.join(self.m_configuration.base_output_USER_dir, self.m_args.score_sub_dir, self.m_configuration.protocol)


  def execute_tool_chain(self, perform_training):
    """Executes the desired tool chain on the local machine"""
    # preprocessing
    if not self.m_args.skip_preprocessing:
      if self.m_args.dry_run:
        print "Would have preprocessed images for protocol %s ..." % self.m_configuration.protocol
      else:
        self.m_tool_chain.preprocess_images(
              self.m_preprocessor,
              force = self.m_args.force)

    # feature extraction
    if perform_training and not self.m_args.skip_extractor_training and hasattr(self.m_extractor, 'train'):
      if self.m_args.dry_run:
        print "Would have trained the extractor ..."
      else:
        self.m_tool_chain.train_extractor(
              self.m_extractor,
              self.m_preprocessor,
              force = self.m_args.force)

    if not self.m_args.skip_extraction:
      if self.m_args.dry_run:
        print "Would have extracted the features for protocol %s ..." % self.m_configuration.protocol
      else:
        self.m_tool_chain.extract_features(
              self.m_extractor,
              self.m_preprocessor,
              force = self.m_args.force)

    # feature projection
    if perform_training and not self.m_args.skip_projector_training and hasattr(self.m_tool, 'train_projector'):
      if self.m_args.dry_run:
        print "Would have trained the projector ..."
      else:
        self.m_tool_chain.train_projector(
              self.m_tool,
              self.m_extractor,
              force = self.m_args.force)

    if not self.m_args.skip_projection and hasattr(self.m_tool, 'project'):
      if self.m_args.dry_run:
        print "Would have projected the features for protocol %s ..." % self.m_configuration.protocol
      else:
        self.m_tool_chain.project_features(
              self.m_tool,
              self.m_extractor,
              force = self.m_args.force)

    # model enrollment
    if perform_training and not self.m_args.skip_enroller_training and hasattr(self.m_tool, 'train_enroller'):
      if self.m_args.dry_run:
        print "Would have trained the enroller ..."
      else:
        self.m_tool_chain.train_enroller(
              self.m_tool,
              self.m_extractor,
              force = self.m_args.force)

    if not self.m_args.skip_enrollment:
      if self.m_args.dry_run:
        print "Would have enrolled the models for protocol %s ..." % self.m_configuration.protocol
      else:
        self.m_tool_chain.enroll_models(
              self.m_tool,
              self.m_extractor,
              compute_zt_norm = False,
              groups = ['dev'], # only dev group
              force = self.m_args.force)

    # score computation
    if not self.m_args.skip_score_computation:
      if self.m_args.dry_run:
        print "Would have computed the scores for protocol %s ..." % self.m_configuration.protocol
      else:
        self.m_tool_chain.compute_scores(
              self.m_tool,
              compute_zt_norm = False,
              groups = ['dev'], # only dev group
              preload_probes = self.m_args.preload_probes,
              force = self.m_args.force)

    if not self.m_args.skip_concatenation:
      if self.m_args.dry_run:
        print "Would have concatenated the scores for protocol %s ..." % self.m_configuration.protocol
      else:
        self.m_tool_chain.concatenate(
              compute_zt_norm = False,
              groups = ['dev']) # only dev group


  def add_jobs_to_grid(self, external_dependencies, external_job_ids, perform_training):
    # collect job ids
    job_ids = {}
    job_ids.update(external_job_ids)

    # if there are any external dependencies, we need to respect them
    deps = external_dependencies[:]
    training_deps = external_dependencies[:]

    default_opt = ' --protocol %s'%self.m_configuration.protocol
    # image preprocessing; never has any dependencies.
    if not self.m_args.skip_preprocessing:
      # preprocessing must be done one after each other
      #   since training files are identical for all protocols
      preprocessing_deps = deps[:]
      if 'preprocessing' in job_ids:
        preprocessing_deps.append(job_ids['preprocessing'])
      job_ids['preprocessing'] = self.submit_grid_job(
              'preprocess' + default_opt,
              name = 'pre-%s' % self.m_configuration.protocol,
              list_to_split = self.m_file_selector.original_image_list(),
              number_of_files_per_job = self.m_grid_config.number_of_images_per_job,
              dependencies = preprocessing_deps,
              **self.m_grid_config.preprocessing_queue)
      deps.append(job_ids['preprocessing'])
      if perform_training:
        training_deps.append(job_ids['preprocessing'])


    # feature extraction training
    if perform_training and not self.m_args.skip_extractor_training and hasattr(self.m_extractor, 'train'):
      job_ids['extraction_training'] = self.submit_grid_job(
              'train-extractor' + default_opt,
              name = 'f-train',
              dependencies = training_deps,
              **self.m_grid_config.training_queue)
      deps.append(job_ids['extraction_training'])

    if not self.m_args.skip_extraction:
      job_ids['feature_extraction'] = self.submit_grid_job(
              'extract' + default_opt,
              name = 'extr-%s' % self.m_configuration.protocol,
              list_to_split = self.m_file_selector.preprocessed_image_list(),
              number_of_files_per_job = self.m_grid_config.number_of_features_per_job,
              dependencies = deps,
              **self.m_grid_config.extraction_queue)
      deps.append(job_ids['feature_extraction'])
      if perform_training:
        training_deps.append(job_ids['feature_extraction'])

    # feature projection training
    if perform_training and not self.m_args.skip_projector_training and hasattr(self.m_tool, 'train_projector'):
      job_ids['projector_training'] = self.submit_grid_job(
              'train-projector' + default_opt,
              name = "p-train",
              dependencies = training_deps,
              **self.m_grid_config.training_queue)
      deps.append(job_ids['projector_training'])

    if not self.m_args.skip_projection and hasattr(self.m_tool, 'project'):
      job_ids['feature_projection'] = self.submit_grid_job(
              'project' + default_opt,
              name="pro-%s" % self.m_configuration.protocol,
              list_to_split = self.m_file_selector.feature_list(),
              number_of_files_per_job = self.m_grid_config.number_of_projections_per_job,
              dependencies = deps,
              **self.m_grid_config.projection_queue)
      deps.append(job_ids['feature_projection'])
      if perform_training:
        training_deps.append(job_ids['feature_projection'])

    # model enrollment training
    if perform_training and not self.m_args.skip_enroller_training and hasattr(self.m_tool, 'train_enroller'):
      job_ids['enrollment_training'] = self.submit_grid_job(
              'train-enroller' + default_opt,
              name="e-train",
              dependencies = training_deps,
              **self.m_grid_config.training_queue)
      deps.append(job_ids['enrollment_training'])

    # enroll models
    if not self.m_args.skip_enrollment:
      job_ids['enroll'] = self.submit_grid_job(
              'enroll' + default_opt,
              name = "enr-%s" % self.m_configuration.protocol,
              list_to_split = self.m_file_selector.model_ids('dev'),
              number_of_files_per_job = self.m_grid_config.number_of_models_per_enroll_job,
              dependencies = deps,
              **self.m_grid_config.enroll_queue)
      deps.append(job_ids['enroll'])

    # compute scores
    if not self.m_args.skip_score_computation:
      job_ids['score'] = self.submit_grid_job(
              'compute-scores' + default_opt,
              name = "score-%s" % self.m_configuration.protocol,
              list_to_split = self.m_file_selector.model_ids('dev'),
              number_of_files_per_job = self.m_grid_config.number_of_models_per_score_job,
              dependencies = deps,
              **self.m_grid_config.score_queue)
      deps.append(job_ids['score'])

    # concatenate results
    if not self.m_args.skip_concatenation:
      job_ids['concatenate'] = self.submit_grid_job(
              'concatenate' + default_opt,
              dependencies = deps,
              name = "concat-%s" % self.m_configuration.protocol)

    # return the job ids, in case anyone wants to know them
    return job_ids


  def execute_grid_job(self):
    """This function executes the grid job that is specified on the command line."""
    # preprocess the images
    if self.m_args.sub_task == 'preprocess':
      self.m_tool_chain.preprocess_images(
          self.m_preprocessor,
          indices = self.indices(self.m_file_selector.original_image_list(), self.m_grid_config.number_of_images_per_job),
          force = self.m_args.force)

    # train the feature extractor
    elif self.m_args.sub_task == 'train-extractor':
      self.m_tool_chain.train_extractor(
          self.m_extractor,
          self.m_preprocessor,
          force = self.m_args.force)

    # extract the features
    elif self.m_args.sub_task == 'extract':
      self.m_tool_chain.extract_features(
          self.m_extractor,
          self.m_preprocessor,
          indices = self.indices(self.m_file_selector.preprocessed_image_list(), self.m_grid_config.number_of_features_per_job),
          force = self.m_args.force)

    # train the feature projector
    elif self.m_args.sub_task == 'train-projector':
      self.m_tool_chain.train_projector(
          self.m_tool,
          self.m_extractor,
          force = self.m_args.force)

    # project the features
    elif self.m_args.sub_task == 'project':
      self.m_tool_chain.project_features(
          self.m_tool,
          self.m_extractor,
          indices = self.indices(self.m_file_selector.preprocessed_image_list(), self.m_grid_config.number_of_projections_per_job),
          force = self.m_args.force)

    # train the model enroller
    elif self.m_args.sub_task == 'train-enroller':
      self.m_tool_chain.train_enroller(
          self.m_tool,
          self.m_extractor,
          force = self.m_args.force)

    # enroll the models
    elif self.m_args.sub_task == 'enroll':
      self.m_tool_chain.enroll_models(
          self.m_tool,
          self.m_extractor,
          indices = self.indices(self.m_file_selector.model_ids('dev'), self.m_grid_config.number_of_models_per_enroll_job),
          compute_zt_norm = False,
          groups = ['dev'],
          force = self.m_args.force)

    # compute scores
    elif self.m_args.sub_task == 'compute-scores':
      self.m_tool_chain.compute_scores(
          self.m_tool,
          indices = self.indices(self.m_file_selector.model_ids('dev'), self.m_grid_config.number_of_models_per_score_job),
          compute_zt_norm = False,
          groups = ['dev'],
          preload_probes = self.m_args.preload_probes,
          force = self.m_args.force)

    # concatenate
    elif self.m_args.sub_task == 'concatenate':
      self.m_tool_chain.concatenate(
          compute_zt_norm = False,
          groups = ['dev'])

    # Test if the keyword was processed
    else:
      raise ValueError("The given subtask '%s' could not be processed. THIS IS A BUG. Please report this to the authors.")


def parse_args(command_line_arguments = sys.argv[1:]):
  """This function parses the given options (which by default are the command line options)"""
  # sorry for that.
  global parameters
  parameters = command_line_arguments

  # set up command line parser
  parser = argparse.ArgumentParser(description=__doc__,
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)

  # add the arguments required for all tool chains
  config_group, dir_group, file_group, sub_dir_group, other_group, skip_group = ToolChainExecutorGBU.required_command_line_options(parser)

  sub_dir_group.add_argument('--model-directory', type = str, metavar = 'DIR', dest='model_dir', default = 'models',
      help = 'Subdirectories (of the --temp-directory) where the models should be stored')

  #######################################################################################
  ############################ other options ############################################
  other_group.add_argument('-F', '--force', action='store_true',
      help = 'Force to erase former data if already exist')
  other_group.add_argument('-w', '--preload-probes', action='store_true', dest='preload_probes',
      help = 'Preload probe files during score computation (needs more memory, but is faster and requires fewer file accesses). WARNING! Use this flag with care!')
  other_group.add_argument('--protocols', type = str, nargs = '+', choices = ['Good', 'Bad', 'Ugly'], default = ['Good', 'Bad', 'Ugly'],
      help = 'The protocols to use, by default all three (Good, Bad, and Ugly) are executed.')

  #######################################################################################
  #################### sub-tasks being executed by this script ##########################
  parser.add_argument('--sub-task',
      choices = ('preprocess', 'train-extractor', 'extract', 'train-projector', 'project', 'train-enroller', 'enroll', 'compute-scores', 'concatenate'),
      help = argparse.SUPPRESS) #'Executes a subtask (FOR INTERNAL USE ONLY!!!)'
  parser.add_argument('--protocol', type=str, choices=['Good','Bad','Ugly'],
      help = argparse.SUPPRESS) #'The protocol which should be used in this sub-task'

  return parser.parse_args(command_line_arguments)


def face_verify(args, external_dependencies = [], external_fake_job_id = 0):
  """This is the main entry point for computing face verification experiments.
  You just have to specify configuration scripts for any of the steps of the toolchain, which are:
  -- the database
  -- feature extraction (including image preprocessing)
  -- the score computation tool
  -- and the grid configuration (in case, the function should be executed in the grid).
  Additionally, you can skip parts of the toolchain by selecting proper --skip-... parameters.
  If your probe files are not too big, you can also specify the --preload-probes switch to speed up the score computation.
  If files should be re-generated, please specify the --force option (might be combined with the --skip-... options)"""

  if args.sub_task:
    # execute the desired sub-task
    executor = ToolChainExecutorGBU(args, protocol=args.protocol)
    executor.execute_grid_job()
    return []

  elif args.grid:

    # get the name of this file
    this_file = __file__
    if this_file[-1] == 'c':
      this_file = this_file[0:-1]

    # initialize the executor to submit the jobs to the grid
    global parameters

    # for the first protocol, we do not have any own dependencies
    dependencies = external_dependencies
    job_ids = {}
    resulting_dependencies = {}
    perform_training = True
    dry_run_init = external_fake_job_id
    for protocol in args.protocols:
      # create an executor object
      executor = ToolChainExecutorGBU(args, protocol)
      executor.set_common_parameters(calling_file = this_file, parameters = parameters, fake_job_id = dry_run_init)

      # add the jobs
      new_job_ids = executor.add_jobs_to_grid(dependencies, job_ids, perform_training)
      job_ids.update(new_job_ids)

      # skip the training for the next protocol
      perform_training = False

      dry_run_init += 30
    # at the end of all protocols, return the list of dependencies
    return job_ids
  else:
    perform_training = True
    # not in a grid, use default tool chain sequentially
    for protocol in args.protocols:
      # generate executor for the current protocol
      executor = ToolChainExecutorGBU(args, protocol)
      # execute the tool chain locally
      executor.execute_tool_chain(perform_training)
      perform_training = False

    # no dependencies since we executed the jobs locally
    return []


def main():
  """Executes the main function"""
  # do the command line parsing
  args = parse_args()
  for f in (args.database, args.preprocessor, args.features, args.tool):
    if not os.path.exists(str(f)):
      raise ValueError("The given file '%s' does not exist."%f)
  # perform face verification test
  face_verify(args)

if __name__ == "__main__":
  main()

