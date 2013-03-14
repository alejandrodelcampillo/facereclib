#!/usr/bin/env python
# vim: set fileencoding=utf-8 :
# Manuel Guenther <Manuel.Guenther@idiap.ch>

import bob
import numpy
import types

from .Tool import Tool
from .UBMGMM import UBMGMMTool, UBMGMMVideoTool
from .. import utils


class ISVTool (UBMGMMTool):
  """Tool chain for computing Unified Background Models and Gaussian Mixture Models of the features"""


  def __init__(
      self,
      # ISV training
      subspace_dimension_of_u,       # U subspace dimension
      jfa_training_iterations = 10,  # Number of EM iterations for the JFA training
      # ISV enrollment
      jfa_enroll_iterations = 1,     # Number of iterations for the enrollment phase
      # parameters of the GMM
      **kwargs
  ):
    """Initializes the local UBM-GMM tool with the given file selector object"""
    # call base class constructor with its set of parameters
    UBMGMMTool.__init__(self, **kwargs)

    # call tool constructor to overwrite what was set before
    Tool.__init__(
        self,
        performs_projection = True,
        use_projected_features_for_enrollment = True,
        requires_enroller_training = False, # not needed anymore because it's done while training the projector
        split_training_features_by_client = True,
    )

    self.m_subspace_dimension_of_u = subspace_dimension_of_u
    self.m_jfa_training_iterations = jfa_training_iterations
    self.m_jfa_enroll_iterations = jfa_enroll_iterations


  def _train_isv(self, train_features):
    utils.info("  -> Projecting training data")
    data2 = []
    for client_features in train_features:
      list = []
      for feature in client_features:
        # Initializes GMMStats object
        self.m_gmm_stats = bob.machine.GMMStats(self.m_ubm.dim_c, self.m_ubm.dim_d)
        list.append(UBMGMMTool.project(self, feature))
      data2.append(list)


    utils.info("  -> Training ISV enroller")
    self.m_jfabase = bob.machine.JFABaseMachine(self.m_ubm, self.m_subspace_dimension_of_u)
    self.m_jfabase.ubm = self.m_ubm

    # train ISV model
    t = bob.trainer.JFABaseTrainer(self.m_jfabase)
    t.train_isv(data2, self.m_jfa_training_iterations, self.m_relevance_factor)


  def train_projector(self, train_features, projector_file):
    """Train Projector and Enroller at the same time"""

    data1 = numpy.vstack([feature for client in train_features for feature in client])

    UBMGMMTool._train_projector_using_array(self, data1)
    # to save some memory, we might want to delete these data
    del data1

    # train ISV
    self._train_isv(train_features)

    # Save the JFA base AND the UBM into the same file
    self._save_projector(projector_file)


  def _save_projector(self, projector_file):

    hdf5file = bob.io.HDF5File(projector_file, "w")
    hdf5file.create_group('Projector')
    hdf5file.cd('Projector')
    self.m_ubm.save(hdf5file)

    hdf5file.cd('/')
    hdf5file.create_group('Enroller')
    hdf5file.cd('Enroller')
    self.m_jfabase.save(hdf5file)



  # Here, we just need to load the UBM from the projector file.
  def load_projector(self, projector_file):
    """Reads the UBM model from file"""

    hdf5file = bob.io.HDF5File(projector_file)

    # Load Projector
    hdf5file.cd('Projector')
    # read UBM
    self.m_ubm = bob.machine.GMMMachine(hdf5file)
    self.m_ubm.set_variance_thresholds(self.m_variance_threshold)
    # Initializes GMMStats object
    self.m_gmm_stats = bob.machine.GMMStats(self.m_ubm.dim_c, self.m_ubm.dim_d)

    hdf5file.cd('/')
    # Load Enroller
    hdf5file.cd('Enroller')
    self.m_jfabase = bob.machine.JFABaseMachine(hdf5file)
    # add UBM model from base class
    self.m_jfabase.ubm = self.m_ubm

    self.m_machine = bob.machine.JFAMachine(self.m_jfabase)
    self.m_base_trainer = bob.trainer.JFABaseTrainer(self.m_jfabase)
    self.m_trainer = bob.trainer.JFATrainer(self.m_machine, self.m_base_trainer)


  #######################################################
  ################ ISV training #########################



  def project(self, feature_array):
    """Computes GMM statistics against a UBM, then corresponding Ux vector"""

    projected_ubm = UBMGMMTool.project(self,feature_array)

    projected_isv = numpy.ndarray(shape=(self.m_ubm.dim_c*self.m_ubm.dim_d,), dtype=numpy.float64)

    model = bob.machine.JFAMachine(self.m_jfabase)
    model.estimate_ux(projected_ubm, projected_isv)
    return [projected_ubm, projected_isv]

  #######################################################
  ################## JFA model enroll ####################

  def save_feature(self, data, feature_file):
    hdf5file = bob.io.HDF5File(feature_file, "w")
    gmmstats = data[0]
    Ux = data[1]
    hdf5file.create_group('gmmstats')
    hdf5file.cd('gmmstats')
    gmmstats.save(hdf5file)
    hdf5file.cd('/')
    hdf5file.set('Ux', Ux)


  def read_feature(self, feature_file):
    """Read the type of features that we require, namely GMMStats"""
    hdf5file = bob.io.HDF5File(feature_file)
    hdf5file.cd('gmmstats')
    gmmstats = bob.machine.GMMStats(hdf5file)
    return gmmstats


  def enroll(self, enroll_features):
    """Performs ISV enrollment"""
    self.m_trainer.enrol(enroll_features, self.m_jfa_enroll_iterations)
    # return the resulting gmm
    return self.m_machine


  ######################################################
  ################ Feature comparison ##################
  def read_model(self, model_file):
    """Reads the JFA Machine that holds the model"""
    machine = bob.machine.JFAMachine(bob.io.HDF5File(model_file))
    machine.jfa_base = self.m_jfabase
    return machine

  def read_probe(self, probe_file):
    """Read the type of features that we require, namely GMMStats"""
    hdf5file = bob.io.HDF5File(probe_file)
    hdf5file.cd('gmmstats')
    gmmstats = bob.machine.GMMStats(hdf5file)
    hdf5file.cd('/')
    Ux = hdf5file.read('Ux')
    return [gmmstats, Ux]

  def score(self, model, probe):
    """Computes the score for the given model and the given probe."""
    gmmstats = probe[0]
    Ux = probe[1]
    return model.forward_ux(gmmstats, Ux)

  def score_for_multiple_probes(self, model, probes):
    """This function computes the score between the given model and several given probe files."""
    # TODO: Implement this function for ISV
    gmmstats_acc = bob.machine.GMMStats(probes[0][0])
    for i in range(1,len(probes)):
      gmmstats_acc += probes[i][0]
    projected_isv_acc = numpy.ndarray(shape=(self.m_ubm.dim_c*self.m_ubm.dim_d,), dtype=numpy.float64)
    model.estimate_ux(gmmstats_acc, projected_isv_acc)
    return model.forward_ux(gmmstats_acc, projected_isv_acc)








# Parent classes:
# - Warning: This class uses multiple inheritance! (Note: Python's resolution rule is: depth-first, left-to-right)
# - ISVTool extends UBMGMMTool by providing some additional methods for training the session variability subspace, etc.
# - UBMGMMVideoTool extends UBMGMMTool to support UBM training/enrollment/testing with video.FrameContainers
#
# Here we extend the parent classes by overriding methods:
# -- read_feature --> overridden (use UBMGMMVideoTool's, to read a video.FrameContainer)
# -- train_projector --> overridden (use UBMGMMVideoTool's)
# -- train_enroller --> overridden (based on ISVTool's, but projects only selected frames)
# -- project --> overridden (use UBMGMMVideoTool's)
# -- enroll --> overridden (based on ISVTool, but first projects only selected frames)
# -- read_model --> inherited from ISVTool (because it's inherited first)
# -- read_probe --> inherited from ISVTool (because it's inherited first)
# -- score --> inherited from ISVTool (because it's inherited first)

class ISVVideoTool (ISVTool, UBMGMMVideoTool):
  """Tool chain for video-to-video face recognition using inter-session variability modelling (ISV)."""

  def __init__(
      self,
      frame_selector_for_projector_training,
      frame_selector_for_projection,
      frame_selector_for_enroll,
       **kwargs
  ):

    # call only one base class constructor...
    ISVTool.__init__(self, **kwargs)

    # call tool constructor to overwrite what was set before
    Tool.__init__(
        self,
        performs_projection = True,
        use_projected_features_for_enrollment = False,
        requires_enroller_training = True
    )

    self.m_frame_selector_for_projector_training = frame_selector_for_projector_training
    self.m_frame_selector_for_projection = frame_selector_for_projection
    self.m_frame_selector_for_enroll = frame_selector_for_enroll

    utils.warn("In its current version, this class has not been tested. Use it with care!")


  # Overrides ISVTool.train_enroller
  def train_enroller(self, train_features, enroller_file):
    utils.debug(" .... ISVVideoTool.train_enroller")
    ########## (same as ISVTool.train_enroller)
    # create a JFABasemachine with the UBM from the base class
    self.m_jfabase = bob.machine.JFABaseMachine(self.m_ubm, self.m_subspace_dimension_of_u)
    self.m_jfabase.ubm = self.m_ubm

    ########## calculate GMM stats from video.FrameContainers, using frame_selector_for_train_enroller
    gmm_stats = []
    for client_features in train_features: # loop over clients
      gmm_stats_client = []
      for frame_container in client_features: # loop over videos of client k
        this_gmm_stats = UBMGMMVideoTool.project(self, frame_container, self.m_frame_selector_for_enroller_training)
        gmm_stats_client.append(this_gmm_stats)
      gmm_stats.append(gmm_stats_client)

    utils.debug(" .... got gmm_stats for " + str(len(gmm_stats)) + " clients")

    ########## (same as ISVTool.train_enroller)
    t = bob.trainer.JFABaseTrainer(self.m_jfabase)
    t.train_isv(gmm_stats, self.m_jfa_training_iterations, self.m_relevance_factor)

    # Save the JFA base AND the UBM into the same file
    self.m_jfabase.save(bob.io.HDF5File(enroller_file, "w"))

  def enroll(self, frame_containers):
    utils.debug(" .... ISVVideoTool.enroll")
    enroll_features = []
    for frame_container in frame_containers:
      this_enroll_features = UBMGMMVideoTool.project(self, frame_container, self.m_frame_selector_for_enroll)
      enroll_features.append(this_enroll_features)
    utils.debug(" .... got " + str(len(enroll_features)) + " enroll_features")

    ########## (same as ISVTool.enroll)
    self.m_trainer.enroll(enroll_features, self.m_jfa_enroll_iterations)
    return self.m_machine

  def read_feature(self, feature_file):
    return UBMGMMVideoTool.read_feature(self,str(feature_file))

  def project(self, frame_container):
    """Computes GMM statistics against a UBM, given an input video.FrameContainer"""
    return UBMGMMVideoTool.project(self,frame_container)

  def train_projector(self, train_files, projector_file):
    """Computes the Universal Background Model from the training ("world") data"""
    return UBMGMMVideoTool.train_projector(self,train_files, projector_file)

