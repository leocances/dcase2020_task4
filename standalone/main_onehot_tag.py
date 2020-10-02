"""
	Main script for testing MixMatch, ReMixMatch, FixMatch or supervised training on a mono-label dataset.
	Available datasets are CIFAR10 and UrbanSound8k.
	They do not have a supervised/unsupervised separation, so we need to split it manually.
"""

import os
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["NUMEXPR_NU M_THREADS"] = "2"
os.environ["OMP_NUM_THREADS"] = "2"

import json
import numpy as np
import os.path as osp
import torch

from argparse import ArgumentParser, Namespace
from time import time
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import transforms
from torchvision.datasets import CIFAR10
from torchvision.transforms import RandomChoice, Compose, ToTensor
from typing import Callable, Dict, List

from augmentation_utils.signal_augmentations import TimeStretch, Occlusion, Noise
from augmentation_utils.spec_augmentations import HorizontalFlip, RandomTimeDropout, RandomFreqDropout
from augmentation_utils.spec_augmentations import Noise as NoiseSpec

from dcase2020.util.utils import get_datetime, reset_seed

from dcase2020_task4.fixmatch.losses.tag.onehot import FixMatchLossOneHot
from dcase2020_task4.fixmatch.trainer import FixMatchTrainer
from dcase2020_task4.fixmatch.trainer_v11 import FixMatchTrainerV11

from dcase2020_task4.mixmatch.losses.tag.onehot import MixMatchLossOneHot
from dcase2020_task4.mixmatch.mixers.tag import MixMatchMixer
from dcase2020_task4.mixmatch.trainer import MixMatchTrainer
from dcase2020_task4.mixmatch.trainer_v3 import MixMatchTrainerV3

from dcase2020_task4.mixup.mixers.tag import MixUpMixerTag

from dcase2020_task4.remixmatch.losses.tag.onehot import ReMixMatchLossOneHot
from dcase2020_task4.remixmatch.mixers.tag import ReMixMatchMixer
from dcase2020_task4.remixmatch.self_label import SelfSupervisedFlips, SelfSupervisedRotation
from dcase2020_task4.remixmatch.trainer import ReMixMatchTrainer

from dcase2020_task4.supervised.trainer import SupervisedTrainer

from dcase2020_task4.util.augments.img_augments import CutOut as CutOutImg, TranslateX, TranslateY
from dcase2020_task4.util.augments.rand_augments import RandAugment
from dcase2020_task4.util.augments.spec_augments import CutOutSpec
from dcase2020_task4.util.avg_distributions import DistributionAlignmentOnehot
from dcase2020_task4.util.checkpoint import CheckPoint
from dcase2020_task4.util.datasets.dataset_idx import get_classes_idx, shuffle_classes_idx, reduce_classes_idx, split_classes_idx
from dcase2020_task4.util.datasets.multiple_dataset import MultipleDataset
from dcase2020_task4.util.datasets.no_label_dataset import NoLabelDataset
from dcase2020_task4.util.datasets.onehot_dataset import OneHotDataset
from dcase2020_task4.util.datasets.random_choice_dataset import RandomChoiceDataset
from dcase2020_task4.util.datasets.smooth_dataset import SmoothOneHotDataset
from dcase2020_task4.util.datasets.to_tensor_dataset import ToTensorDataset
from dcase2020_task4.util.guessers.batch import GuesserModelArgmax, GuesserModelArgmaxSmooth, GuesserMeanModelArgmax, \
	GuesserModelAlignmentSharpen, GuesserMeanModelSharpen
from dcase2020_task4.util.other_metrics import CategoricalAccuracyOnehot, FnMetric
from dcase2020_task4.util.ramp_up import RampUp
from dcase2020_task4.util.sharpen import Sharpen
from dcase2020_task4.util.types import str_to_bool, str_to_optional_str, str_to_union_str_int, str_to_optional_int, \
	str_to_optional_float
from dcase2020_task4.util.uniloss import ConstantEpochUniloss, WeightLinearUniloss, WeightLinearUnilossStepper
from dcase2020_task4.util.utils_match import cross_entropy
from dcase2020_task4.util.utils_standalone import post_process_args, check_args, build_writer_from_args, save_and_close_writer, \
	save_args, save_augms, build_model_from_args, build_optim_from_args, build_sched_from_args, get_nb_parameters
from dcase2020_task4.util.zip_cycle import ZipCycle

from dcase2020_task4.learner import Learner
from dcase2020_task4.validator import ValidatorTag

from metric_utils.metrics import Metrics

from ubs8k.datasets import Dataset as UBS8KDataset
from ubs8k.datasetManager import DatasetManager as UBS8KDatasetManager


def create_args() -> Namespace:
	parser = ArgumentParser()
	parser.add_argument("--run", type=str, default=None,
						choices=["fixmatch", "fm", "mixmatch", "mm", "remixmatch", "rmm", "supervised_full", "sf", "supervised_part", "sp"],
						help="Training method to run.")
	parser.add_argument("--seed", type=int, default=123)
	parser.add_argument("--debug_mode", type=str_to_bool, default=False)
	parser.add_argument("--suffix", type=str, default="",
						help="Suffix to Tensorboard log dir.")

	parser.add_argument("--dataset_path", type=str, default=osp.join("..", "dataset", "CIFAR10"))
	parser.add_argument("--dataset_name", type=str, default="CIFAR10", choices=["CIFAR10", "UBS8K"])
	parser.add_argument("--nb_classes", type=int, default=10)

	parser.add_argument("--logdir", type=str, default=osp.join("..", "..", "tensorboard"))
	parser.add_argument("--model", type=str, default="WideResNet28Rot",
						choices=["WideResNet28Rot", "CNN03Rot", "VGG11Rot"])
	parser.add_argument("--nb_epochs", type=int, default=300)

	parser.add_argument("--batch_size_s", type=int, default=64,
						help="Batch size used for supervised loader.")
	parser.add_argument("--batch_size_u", type=int, default=64,
						help="Batch size used for unsupervised loader.")
	parser.add_argument("--num_workers_s", type=int, default=4,
						help="Number of workers created by supervised loader.")
	parser.add_argument("--num_workers_u", type=int, default=4,
						help="Number of workers created by unsupervised loader.")

	parser.add_argument("--optimizer", type=str, default="Adam",
						choices=["Adam", "SGD", "RAdam", "PlainRAdam", "AdamW"],
						help="Optimizer used.")
	parser.add_argument("--scheduler", type=str_to_optional_str, default="Cosine",
						choices=[None, "CosineLRScheduler", "Cosine", "StepLRScheduler", "Step", "MultiStepLR"],
						help="FixMatch scheduler used. Use \"None\" for constant learning rate.")

	parser.add_argument("--lr", "--learning_rate", type=float, default=1e-3,
						help="Learning rate used.")
	parser.add_argument("--weight_decay", "--wd", type=str_to_optional_float, default=None,
						help="Weight decay used.")
	parser.add_argument("--momentum", type=str_to_optional_float, default=None,
						help="Momentum used in SGD optimizer.")

	parser.add_argument("--lr_decay_ratio", type=float, default=0.2,
						help="Learning rate decay ratio used in StepLRScheduler.")
	parser.add_argument("--epoch_steps", type=int, nargs="+", default=[60, 120, 160],
						help="Epochs where we decrease the learning rate. Used in StepLRScheduler.")

	parser.add_argument("--write_results", type=str_to_bool, default=True,
						help="Write results in a tensorboard SummaryWriter.")
	parser.add_argument("--args_filepaths", type=str, nargs="*", default=None,
						help="List of filepaths to arguments file. Values in this JSON will overwrite other options in terminal.")
	parser.add_argument("--checkpoint_path", type=str, default=osp.join("..", "models"),
						help="Directory path where checkpoint models will be saved.")
	parser.add_argument("--checkpoint_metric_name", type=str, default="acc",
						choices=["acc"],
						help="Metric used to compare and save best model during training.")

	parser.add_argument("--use_rampup", "--use_warmup", type=str_to_bool, default=False,
						help="Use RampUp or not for lambda_u and lambda_u1 hyperparameters.")
	parser.add_argument("--nb_rampup_steps", type=str_to_union_str_int, default="nb_epochs",
						help="Nb of steps when lambda_u and lambda_u1 is increase from 0 to their value."
							 "Use 0 for deactivate RampUp. Use \"nb_epochs\" for ramping up during all training.")
	parser.add_argument("--rampup_each_epoch", type=str_to_bool, default=True,
						help="If true, update RampUp each epoch, otherwise step each iteration.")

	parser.add_argument("--lambda_s", type=float, default=1.0,
						help="MixMatch, FixMatch and ReMixMatch \"lambda_s\" hyperparameter. Coefficient of supervised loss component.")
	parser.add_argument("--lambda_u", type=float, default=1.0,
						help="MixMatch, FixMatch and ReMixMatch \"lambda_u\" hyperparameter. Coefficient of unsupervised loss component.")
	parser.add_argument("--lambda_u1", type=float, default=0.5,
						help="ReMixMatch \"lambda_u1\" hyperparameter. Coefficient of direct unsupervised loss component.")
	parser.add_argument("--lambda_r", type=float, default=0.5,
						help="ReMixMatch \"lambda_r\" hyperparameter. Coefficient of rotation loss component.")

	parser.add_argument("--nb_augms", type=int, default=2,
						help="Nb of augmentations used in MixMatch.")
	parser.add_argument("--nb_augms_strong", type=int, default=8,
						help="Nb of strong augmentations used in ReMixMatch.")
	parser.add_argument("--history_size", type=int, default=128 * 64,
						help="Nb of predictions kept in AvgDistributions used in ReMixMatch.")

	parser.add_argument("--threshold_confidence", type=float, default=0.95,
						help="FixMatch threshold for compute confidence mask in loss.")
	parser.add_argument("--criterion_name_u", type=str, default="ce",
						choices=["sq_diff", "cross_entropy", "ce"],
						help="MixMatch unsupervised loss component.")

	parser.add_argument("--sharpen_temperature", "--temperature", type=float, default=0.5,
						help="MixMatch and ReMixMatch hyperparameter temperature used by sharpening.")
	parser.add_argument("--mixup_alpha", "--alpha", type=float, default=0.75,
						help="MixMatch and ReMixMatch hyperparameter \"alpha\" used by MixUp.")
	parser.add_argument("--mixup_distribution_name", type=str, default="beta",
						choices=["beta", "uniform", "constant"],
						help="MixUp distribution used in MixMatch and ReMixMatch.")
	parser.add_argument("--shuffle_s_with_u", type=str_to_bool, default=True,
						help="MixMatch shuffle supervised and unsupervised data.")

	parser.add_argument("--dataset_ratio", type=float, default=1.0,
						help="Ratio of the dataset used for training.")
	parser.add_argument("--supervised_ratio", type=float, default=0.1,
						help="Supervised ratio used for split dataset.")

	parser.add_argument("--cross_validation", type=str_to_bool, default=False,
						help="Use cross validation for UBS8K dataset.")
	parser.add_argument("--fold_val", type=int, default=10,
						help="Fold used for validation in UBS8K dataset. This parameter is unused if cross validation is True.")

	parser.add_argument("--ra_magnitude", type=str_to_optional_int, default=None,
						help="Magnitude used in RandAugment. Use \"None\" for generate a random "
							 "magnitude each time the augmentation is called.")
	parser.add_argument("--ra_nb_choices", type=int, default=1,
						help="Nb augmentations composed for RandAugment. ")

	parser.add_argument("--dropout", type=float, default=0.5,
						help="Dropout used in model. WARNING: All models does not use this dropout argument.")
	parser.add_argument("--supervised_augment", type=str_to_optional_str, default=None,
						choices=[None, "weak", "strong"],
						help="Apply identity, weak or strong augment on supervised train dataset.")
	parser.add_argument("--standardize", type=str_to_bool, default=False,
						help="Normalize CIFAR10 data. Currently unused on UBS8K.")

	parser.add_argument("--label_smoothing", type=float, default=0.0,
						help="Label smoothing value for supervised trainings. Use 0.0 for deactivate label smoothing.")
	parser.add_argument("--nb_classes_self_supervised", type=int, default=4,
						help="Nb classes in rotation loss (Self-Supervised part) of ReMixMatch.")
	parser.add_argument("--self_supervised_component", type=str_to_optional_str, default="flips",
						choices=[None, "rotation", "flips"],
						help="Self supervised component applied in ReMixMatch training.")

	# Experimental modes
	# FMV11
	parser.add_argument("--mean_guesser", type=str_to_bool, default=False,
						help="Experimental mode for FixMatch training (FMV11). "
							"Use a mean of predictions to compute artificial label.")
	# MMV8
	parser.add_argument("--use_ceu_1", type=str_to_bool, default=False,
						help="Experimental mode for MixMatch training (MMV8). "
							"Use Constant Epoch Uniloss (ceu) for only 1 loss per epoch : supervised-mixed.")
	# MMV9
	parser.add_argument("--use_ceu_2", type=str_to_bool, default=False,
						help="Experimental mode for MixMatch training (MMV9). "
							"Use Constant Epoch Uniloss (ceu) for only 1 loss per epoch : supervised-mixed-unsupervised.")
	parser.add_argument("--direct_labelisation", type=str_to_bool, default=False,
						help="Experimental mode for MixMatch training (MMV3). "
							"Use artificial label with NON-AUGMENTED batch unsupervised.")

	# MMV18, FMV14
	parser.add_argument("--use_wlu", "--use_weight_linear_uniloss", type=str_to_bool, default=False,
						help="Activate Weight Linear Uniloss experimental mode.")
	parser.add_argument("--wlu_on_epoch", type=str_to_bool, default=True,
						help="Update WLU on iteration or on epoch.")
	parser.add_argument("--wlu_steps", type=int, default=10,
						help="Weight Linear Uniloss nb steps.")

	return parser.parse_args()


def main():
	# Initialisation
	start_time = time()
	start_date = get_datetime()

	args = create_args()
	args = post_process_args(args)
	check_args(args)

	reset_seed(args.seed)
	torch.autograd.set_detect_anomaly(args.debug_mode)

	print("Start match_onehot. (suffix: \"%s\")" % args.suffix)
	print(" - start_date: %s" % start_date)

	print("Arguments :")
	for name, value in args.__dict__.items():
		print(" - %s: %s" % (name, str(value)))

	# Get default metrics used in training and validation
	metrics_s, metrics_u, metrics_u1, metrics_r, metrics_val = build_metrics_from_args(args)
	cross_validation_results = {}

	# Get default activation function
	# Use clamp for avoiding floating precision problems causing NaN loss
	acti_fn = lambda x, dim: x.softmax(dim=dim).clamp(min=2e-30)

	# Main function for running training on CIFAR10 or UrbanSound8K (UBS8K)
	def run(fold_val_ubs8k: int):
		# Get datasets and augments
		if args.dataset_name.lower() == "cifar10":
			augm_list_weak, augm_list_strong = get_cifar10_augms(args)
			dataset_train, dataset_val, dataset_train_augm_weak, dataset_train_augm_strong = \
				get_cifar10_datasets(args, augm_list_weak, augm_list_strong)
		elif args.dataset_name.lower() == "ubs8k":
			augm_list_weak, augm_list_strong = get_ubs8k_augms(args)
			dataset_train, dataset_val, dataset_train_augm_weak, dataset_train_augm_strong = \
				get_ubs8k_datasets(args, fold_val_ubs8k, augm_list_weak, augm_list_strong)
		else:
			raise RuntimeError("Unknown dataset \"%s\"" % args.dataset_name)

		sub_loaders_ratios = [args.supervised_ratio, 1.0 - args.supervised_ratio]

		# Compute sub-indexes for split train dataset in labeled/unlabeled dataset
		cls_idx_all = get_classes_idx(dataset_train, args.nb_classes)
		cls_idx_all = shuffle_classes_idx(cls_idx_all)
		cls_idx_all = reduce_classes_idx(cls_idx_all, args.dataset_ratio)
		idx_train_s, idx_train_u = split_classes_idx(cls_idx_all, sub_loaders_ratios)

		idx_val = list(range(int(len(dataset_val) * args.dataset_ratio)))

		# Convert labels from index to one-hot
		dataset_train = OneHotDataset(dataset_train, args.nb_classes)
		dataset_val = OneHotDataset(dataset_val, args.nb_classes)
		dataset_train_augm_weak = OneHotDataset(dataset_train_augm_weak, args.nb_classes)
		dataset_train_augm_strong = OneHotDataset(dataset_train_augm_strong, args.nb_classes)

		if args.label_smoothing > 0.0:
			dataset_train = SmoothOneHotDataset(dataset_train, args.nb_classes, args.label_smoothing)
			dataset_val = SmoothOneHotDataset(dataset_val, args.nb_classes, args.label_smoothing)
			dataset_train_augm_weak = SmoothOneHotDataset(dataset_train_augm_weak, args.nb_classes, args.label_smoothing)
			dataset_train_augm_strong = SmoothOneHotDataset(dataset_train_augm_strong, args.nb_classes, args.label_smoothing)

		dataset_val = Subset(dataset_val, idx_val)
		loader_val = DataLoader(dataset_val, batch_size=args.batch_size_s, shuffle=False, drop_last=True)

		args_loader_train_s = dict(
			batch_size=args.batch_size_s, shuffle=True, num_workers=args.num_workers_s, drop_last=True)
		args_loader_train_u = dict(
			batch_size=args.batch_size_u, shuffle=True, num_workers=args.num_workers_u, drop_last=True)

		# Create model, optimizer and learning rate scheduler.
		model = build_model_from_args(args)
		optim = build_optim_from_args(args, model)
		sched = build_sched_from_args(args, optim)

		print("%s: %d train examples supervised, %d train examples unsupervised, %d validation examples" % (
			args.dataset_name, len(idx_train_s), len(idx_train_u), len(idx_val)))
		print("Model selected : %s (%d parameters)." % (args.model, get_nb_parameters(model)))

		if args.write_results:
			suffix = "" if args.dataset_name == "CIFAR10" else "%d" % fold_val_ubs8k
			writer = build_writer_from_args(args, start_date, suffix)
		else:
			writer = None

		steppables_iteration = []
		steppables_epoch = []

		# Create RampUp object for warm up an hyperparameter.
		# Must set a target object and be called at each end of epoch or iteration.
		if args.use_rampup:
			rampup_lambda_u = RampUp(args.nb_rampup_steps, args.lambda_u, obj=None, attr_name="lambda_u")
			rampup_lambda_u1 = RampUp(args.nb_rampup_steps, args.lambda_u1, obj=None, attr_name="lambda_u1")
			rampup_lambda_r = RampUp(args.nb_rampup_steps, args.lambda_r, obj=None, attr_name="lambda_r")

			if args.rampup_each_epoch:
				steppables_epoch.append(rampup_lambda_u)
				steppables_epoch.append(rampup_lambda_u1)
				steppables_epoch.append(rampup_lambda_r)
			else:
				steppables_iteration.append(rampup_lambda_u)
				steppables_iteration.append(rampup_lambda_u1)
				steppables_iteration.append(rampup_lambda_r)
		else:
			rampup_lambda_u = None
			rampup_lambda_u1 = None
			rampup_lambda_r = None

		if args.use_wlu:
			# Create experimental Weight Linear Uniloss classes
			nb_steps_wlu = args.wlu_steps if args.wlu_on_epoch else args.nb_epochs * len(idx_train_u) * args.batch_size_u

			wlu = WeightLinearUniloss(nb_steps_wlu, None)
			wlu_stepper = WeightLinearUnilossStepper(args.nb_epochs, nb_steps_wlu, wlu)

			if args.wlu_on_epoch:
				steppables_epoch.append(wlu_stepper)
			else:
				steppables_iteration.append(wlu_stepper)
			steppables_iteration.append(wlu)
		else:
			wlu = None

		steppables_epoch.append(sched)

		if args.run in ["fm", "fixmatch"]:
			dataset_train_s_augm_weak = Subset(dataset_train_augm_weak, idx_train_s)

			dataset_train_u_augm_weak = Subset(dataset_train_augm_weak, idx_train_u)
			dataset_train_u_augm_weak = NoLabelDataset(dataset_train_u_augm_weak)

			dataset_train_u_augm_strong = Subset(dataset_train_augm_strong, idx_train_u)
			dataset_train_u_augm_strong = NoLabelDataset(dataset_train_u_augm_strong)

			if args.mean_guesser:
				dataset_train_u_augm_weak = MultipleDataset([dataset_train_u_augm_weak] * args.nb_augms)

			dataset_train_u_augms_weak_strong = MultipleDataset([dataset_train_u_augm_weak, dataset_train_u_augm_strong])

			loader_train_s_augm_weak = DataLoader(dataset=dataset_train_s_augm_weak, **args_loader_train_s)
			loader_train_u_augms_weak_strong = DataLoader(dataset=dataset_train_u_augms_weak_strong, **args_loader_train_u)
			loader = ZipCycle([loader_train_s_augm_weak, loader_train_u_augms_weak_strong])

			criterion = FixMatchLossOneHot.from_args(args)
			if rampup_lambda_u is not None:
				rampup_lambda_u.set_obj(criterion)

			if args.use_wlu:
				targets_wlu = [
					(criterion, "lambda_s", args.lambda_s, 1.0, 0.0),
					(criterion, "lambda_u", args.lambda_u, 0.0, 1.0),
				]
				wlu.set_targets(targets_wlu)

			if not args.mean_guesser:
				if args.label_smoothing > 0.0:
					guesser = GuesserModelArgmaxSmooth(model, acti_fn, args.label_smoothing, args.nb_classes)
				else:
					guesser = GuesserModelArgmax(model, acti_fn)

				trainer = FixMatchTrainer(
					model, acti_fn, optim, loader, criterion, guesser, metrics_s, metrics_u,
					writer, steppables_iteration
				)
			else:
				# FMV11
				guesser = GuesserMeanModelArgmax(model, acti_fn)
				trainer = FixMatchTrainerV11(
					model, acti_fn, optim, loader, criterion, guesser, metrics_s, metrics_u,
					writer, steppables_iteration
				)

		elif args.run in ["mm", "mixmatch"]:
			dataset_train_s_augm_weak = Subset(dataset_train_augm_weak, idx_train_s)
			dataset_train_u_augm_weak = Subset(dataset_train_augm_weak, idx_train_u)

			dataset_train_u_augm = NoLabelDataset(dataset_train_u_augm_weak)
			dataset_train_u_augms = MultipleDataset([dataset_train_u_augm] * args.nb_augms)

			if args.direct_labelisation:
				dataset_train_u = Subset(dataset_train, idx_train_u)
				dataset_train_u = NoLabelDataset(dataset_train_u)
				dataset_train_u_augms = MultipleDataset([dataset_train_u_augms, dataset_train_u])

			loader_train_s_augm = DataLoader(dataset=dataset_train_s_augm_weak, **args_loader_train_s)
			loader_train_u_augms = DataLoader(dataset=dataset_train_u_augms, **args_loader_train_u)
			loader = ZipCycle([loader_train_s_augm, loader_train_u_augms])

			if loader_train_s_augm.batch_size != loader_train_u_augms.batch_size:
				raise RuntimeError("Supervised and unsupervised batch size must be equal. (%d != %d)" % (
					loader_train_s_augm.batch_size, loader_train_u_augms.batch_size))

			criterion = MixMatchLossOneHot.from_args(args)
			if rampup_lambda_u is not None:
				rampup_lambda_u.set_obj(criterion)
			mixup_mixer = MixUpMixerTag.from_args(args)
			mixer = MixMatchMixer(mixup_mixer, args.shuffle_s_with_u)

			sharpen_fn = Sharpen(args.sharpen_temperature)
			guesser = GuesserMeanModelSharpen(model, acti_fn, sharpen_fn)
			if not args.rampup_each_epoch:
				steppables_iteration.append(rampup_lambda_u)

			if args.use_ceu_1 or args.use_ceu_2:
				if args.use_rampup:
					raise RuntimeError("Experimental MMV8 (or MMV9) cannot be used with RampUp.")
				if args.nb_epochs < 10:
					raise RuntimeError("Cannot train with MMV8 (or MMV9) with less than %d epochs." % 10)

				begin_only_s = 0
				begin_uniform_s_u = int(args.nb_epochs * 0.1)
				begin_only_u = int(args.nb_epochs * 0.9)

				attributes = [(criterion, "lambda_s"), (criterion, "lambda_u")]

				if args.use_ceu_1:
					ratios_range = [
						([1.0, 0.0], begin_only_s, begin_uniform_s_u - 1),
						([0.5, 0.5], begin_uniform_s_u, begin_only_u - 1),
						([0.0, 1.0], begin_only_u, args.nb_epochs),
					]
				elif args.use_ceu_2:
					ratios_range = [
						([1.0, 0.0], begin_only_s, begin_uniform_s_u - 1),
						([0.5, 0.5], begin_uniform_s_u, args.nb_epochs),
					]
				else:
					raise RuntimeError("Invalid ConstantEpochUniloss mode.")

				constant_epoch_uniloss = ConstantEpochUniloss(attributes, ratios_range)
				steppables_epoch.append(constant_epoch_uniloss)

			if args.use_wlu:
				targets_wlu = [
					(criterion, "lambda_s", args.lambda_s, 1.0, 0.0),
					(criterion, "lambda_u", args.lambda_u, 0.0, 1.0),
				]
				wlu.set_targets(targets_wlu)

			if not args.direct_labelisation:
				trainer = MixMatchTrainer(
					model, acti_fn, optim, loader, criterion, guesser, metrics_s, metrics_u,
					writer, mixer, steppables_iteration
				)
			else:
				trainer = MixMatchTrainerV3(
					model, acti_fn, optim, loader, criterion, guesser, metrics_s, metrics_u,
					writer, mixer, steppables_iteration
				)

		elif args.run in ["rmm", "remixmatch"]:
			dataset_train_s_augm_strong = Subset(dataset_train_augm_strong, idx_train_s)
			dataset_train_u_augm_weak = Subset(dataset_train_augm_weak, idx_train_u)
			dataset_train_u_augm_strong = Subset(dataset_train_augm_strong, idx_train_u)

			dataset_train_u_augm_weak = NoLabelDataset(dataset_train_u_augm_weak)
			dataset_train_u_augm_strong = NoLabelDataset(dataset_train_u_augm_strong)

			dataset_train_u_strongs = MultipleDataset([dataset_train_u_augm_strong] * args.nb_augms_strong)
			dataset_train_u_weak_strongs = MultipleDataset([dataset_train_u_augm_weak, dataset_train_u_strongs])

			loader_train_s_strong = DataLoader(dataset_train_s_augm_strong, **args_loader_train_s)
			loader_train_u_augms_weak_strongs = DataLoader(dataset_train_u_weak_strongs, **args_loader_train_u)
			loader = ZipCycle([loader_train_s_strong, loader_train_u_augms_weak_strongs])

			if loader_train_s_strong.batch_size != loader_train_u_augms_weak_strongs.batch_size:
				raise RuntimeError("Supervised and unsupervised batch size must be equal. (%d != %d)" % (
					loader_train_s_strong.batch_size, loader_train_u_augms_weak_strongs.batch_size)
				)

			criterion = ReMixMatchLossOneHot.from_args(args)
			if rampup_lambda_u is not None:
				rampup_lambda_u.set_obj(criterion)
			if rampup_lambda_u1 is not None:
				rampup_lambda_u1.set_obj(criterion)
			if rampup_lambda_r is not None:
				rampup_lambda_r.set_obj(criterion)

			mixup_mixer = MixUpMixerTag.from_args(args)
			mixer = ReMixMatchMixer(mixup_mixer, args.shuffle_s_with_u)

			sharpen_fn = Sharpen(args.sharpen_temperature)
			distributions = DistributionAlignmentOnehot.from_args(args)
			guesser = GuesserModelAlignmentSharpen(model, acti_fn, distributions, sharpen_fn)

			acti_rot_fn = lambda batch, dim: batch.softmax(dim=dim).clamp(min=2e-30)

			if args.self_supervised_component == "rotation":
				ss_transform = SelfSupervisedRotation()
			elif args.self_supervised_component == "flips":
				ss_transform = SelfSupervisedFlips()
			elif args.self_supervised_component is None:
				ss_transform = None
			else:
				raise RuntimeError("Invalid argument \"self_supervised_component = %s\"." % args.self_supervised_component)

			if ss_transform is not None and ss_transform.get_nb_classes() != args.nb_classes_self_supervised:
				raise RuntimeError("Invalid self supervised transform.")

			if not args.rampup_each_epoch:
				steppables_iteration.append(rampup_lambda_u)
				steppables_iteration.append(rampup_lambda_u1)
				steppables_iteration.append(rampup_lambda_r)

			if args.use_wlu:
				targets_wlu = [
					(criterion, "lambda_s", args.lambda_s, 1.0, 0.0),
					(criterion, "lambda_u", args.lambda_u, 0.0, 1.0 / 3.0),
					(criterion, "lambda_u1", args.lambda_u1, 0.0, 1.0 / 3.0),
					(criterion, "lambda_r", args.lambda_r, 0.0, 1.0 / 3.0),
				]
				wlu.set_targets(targets_wlu)

			trainer = ReMixMatchTrainer(
				model, acti_fn, acti_rot_fn, optim, loader, criterion, guesser,
				metrics_s, metrics_u, metrics_u1, metrics_r,
				writer, mixer, distributions, ss_transform, steppables_iteration
			)

		elif args.run in ["sf", "supervised_full"]:
			if args.supervised_augment is None:
				dataset_train_full = dataset_train
			elif args.supervised_augment == "weak":
				dataset_train_full = dataset_train_augm_weak
			elif args.supervised_augment == "strong":
				dataset_train_full = dataset_train_augm_strong
			else:
				raise RuntimeError("Invalid supervised augment choice \"%s\"." % str(args.supervised_augment))

			dataset_train_full = Subset(dataset_train_full, idx_train_s + idx_train_u)
			loader_train_full = DataLoader(dataset_train_full, **args_loader_train_s)

			criterion = cross_entropy

			trainer = SupervisedTrainer(
				model, acti_fn, optim, loader_train_full, criterion, metrics_s, writer
			)

		elif args.run in ["sp", "supervised_part"]:
			if args.supervised_augment is None:
				dataset_train_part = dataset_train
			elif args.supervised_augment == "weak":
				dataset_train_part = dataset_train_augm_weak
			elif args.supervised_augment == "strong":
				dataset_train_part = dataset_train_augm_strong
			else:
				raise RuntimeError("Invalid supervised augment choice \"%s\"." % str(args.supervised_augment))

			dataset_train_part = Subset(dataset_train_part, idx_train_s)
			loader_train_part = DataLoader(dataset_train_part, **args_loader_train_s)

			criterion = cross_entropy

			trainer = SupervisedTrainer(
				model, acti_fn, optim, loader_train_part, criterion, metrics_s, writer
			)

		else:
			raise RuntimeError("Unknown run %s" % args.run)

		# Prepare checkpoint for saving best model during training
		if args.write_results:
			filename_model = "%s_%s_%s.torch" % (args.model, args.train_name, args.suffix)
			filepath_model = osp.join(args.checkpoint_path, filename_model)
			checkpoint = CheckPoint(model, optim, name=filepath_model)
		else:
			checkpoint = None

		validator = ValidatorTag(
			model, acti_fn, loader_val, metrics_val, writer, checkpoint, args.checkpoint_metric_name
		)

		# Filter steppables that are None
		steppables_epoch = [steppable for steppable in steppables_epoch if steppable is not None]

		# Build Learner and start the main loop for training and validation
		learner = Learner(args.train_name, trainer, validator, args.nb_epochs, steppables_epoch)
		learner.start()

		# Save results
		if writer is not None:
			augments_dict = {"augm_weak": augm_list_weak, "augm_strong": augm_list_strong}

			save_and_close_writer(writer, args, augments_dict)

			filepath_args = osp.join(writer.log_dir, "args.json")
			save_args(filepath_args, args)

			filepath_augms = osp.join(writer.log_dir, "augments.json")
			save_augms(filepath_augms, augments_dict)

		recorder = validator.get_metrics_recorder()
		recorder.print_min_max()

		maxs = recorder.get_maxs()
		cross_validation_results[fold_val_ubs8k] = maxs["acc"]

	if not args.cross_validation:
		run(args.fold_val)
	else:
		for fold_val_i_ubs8k_ in range(1, 11):
			run(fold_val_i_ubs8k_)

		# Print cross-val results
		cross_val_results_messages = [(" %d: %f" % (fold, value)) for fold, value in cross_validation_results.items()]
		mean_ = np.mean(list(cross_validation_results.values()))
		print("\n")
		print("Cross-validation results : \n", "\n".join(cross_val_results_messages))
		print("Cross-validation mean : ", mean_)

		# Save cross-val results
		if args.write_results:
			filepath = osp.join(args.logdir, "cross_val_results_%s_%s.json" % (args.suffix, start_date))
			content = {"results": cross_validation_results, "mean": mean_}
			with open(filepath, "w") as file:
				json.dump(content, file, indent="\t")

	exec_time = time() - start_time
	print("")
	print("Program started at \"%s\" and terminated at \"%s\"." % (start_date, get_datetime()))
	print("Total execution time: %.2fs" % exec_time)
	# End of main()


def build_metrics_from_args(args: Namespace) -> List[Dict[str, Metrics]]:
	metrics_s = {
		"s_acc": CategoricalAccuracyOnehot(dim=1),
	}
	metrics_u = {
		"u_acc": CategoricalAccuracyOnehot(dim=1),
	}
	metrics_u1 = {
		"u1_acc": CategoricalAccuracyOnehot(dim=1),
	}
	metrics_r = {
		"r_acc": CategoricalAccuracyOnehot(dim=1),
	}
	metrics_val = {
		"acc": CategoricalAccuracyOnehot(dim=1),
		"ce": FnMetric(cross_entropy),
	}
	return [metrics_s, metrics_u, metrics_u1, metrics_r, metrics_val]


def get_cifar10_augms(args: Namespace) -> (List[Callable], List[Callable]):
	ratio_augm_weak = 0.5
	augm_list_weak = [
		HorizontalFlip(ratio_augm_weak),
		CutOutImg(ratio_augm_weak, rect_width_scale_range=(0.1, 0.1), rect_height_scale_range=(0.1, 0.1), fill_value=0),
		TranslateX(ratio_augm_weak, deltas=(2/32, 6/32)),
		TranslateY(ratio_augm_weak, deltas=(2/32, 6/32)),
	]
	ratio_augm_strong = 1.0
	augm_list_strong = [
		CutOutImg(ratio_augm_strong, rect_width_scale_range=(0.25, 0.75), rect_height_scale_range=(0.25, 0.75), fill_value=0),
		RandAugment(ratio=ratio_augm_strong, magnitude_m=args.ra_magnitude, nb_choices_n=args.ra_nb_choices),
	]

	return augm_list_weak, augm_list_strong


def get_cifar10_datasets(
	args: Namespace, augm_list_weak: List[Callable], augm_list_strong: List[Callable]
) -> (Dataset, Dataset, Dataset, Dataset):
	# Add preprocessing before each augmentation
	pre_process_fn = lambda img: np.array(img)
	# Add postprocessing after each augmentation (shape : [32, 32, 3] -> [3, 32, 32])
	post_process_fn = lambda img: img.transpose()

	if args.standardize:
		# normalize_fn = Normalize(original_range=(0, 255), target_range=(0, 1))
		# standardize_fn = Standardize([0.4914, 0.4822, 0.4465], [0.2023, 0.1994, 0.2010])
		# post_process_fn = Compose([normalize_fn, standardize_fn, post_process_fn])

		pre_process_fn = lambda img: img
		post_process_fn = Compose([
			ToTensor(),
			transforms.Normalize(np.array([125.3, 123.0, 113.9]) / 255.0, np.array([63.0, 62.1, 66.7]) / 255.0),
		])

	# Prepare TRAIN data
	transforms_train = [pre_process_fn, post_process_fn]
	dataset_train = CIFAR10(
		args.dataset_path, train=True, download=True, transform=Compose(transforms_train))

	# Prepare VALIDATION data
	transforms_val = [pre_process_fn, post_process_fn]
	dataset_val = CIFAR10(
		args.dataset_path, train=False, download=True, transform=Compose(transforms_val))

	# Prepare WEAKLY AUGMENTED TRAIN data
	augm_weak_fn = RandomChoice(augm_list_weak)
	transforms_train_weak = [pre_process_fn, augm_weak_fn, post_process_fn]
	dataset_train_augm_weak = CIFAR10(
		args.dataset_path, train=True, download=True, transform=Compose(transforms_train_weak))

	# Prepare STRONGLY AUGMENTED TRAIN data
	augm_strong_fn = RandomChoice(augm_list_strong)
	transforms_train_strong = [pre_process_fn, augm_strong_fn, post_process_fn]
	dataset_train_augm_strong = CIFAR10(
		args.dataset_path, train=True, download=True, transform=Compose(transforms_train_strong))

	return dataset_train, dataset_val, dataset_train_augm_weak, dataset_train_augm_strong


def get_ubs8k_augms(args: Namespace) -> (List[Callable], List[Callable]):
	ratio_augm_weak = 0.5
	augm_list_weak = [
		HorizontalFlip(ratio_augm_weak),
		Occlusion(ratio_augm_weak, max_size=1.0),
	]
	ratio_augm_strong = 1.0
	augm_list_strong = [
		TimeStretch(ratio_augm_strong),
		Noise(ratio_augm_strong, target_snr=15),
		CutOutSpec(ratio_augm_strong, rect_width_scale_range=(0.1, 0.25), rect_height_scale_range=(0.1, 0.25)),
		RandomTimeDropout(ratio_augm_strong, dropout=0.01),
		RandomFreqDropout(ratio_augm_strong, dropout=0.01),
		NoiseSpec(ratio_augm_strong, snr=5.0),
	]

	return augm_list_weak, augm_list_strong


def get_ubs8k_datasets(
	args: Namespace, fold_val: int, augm_list_weak: List[Callable], augm_list_strong: List[Callable]
) -> (Dataset, Dataset, Dataset, Dataset):
	metadata_root = osp.join(args.dataset_path, "metadata")
	audio_root = osp.join(args.dataset_path, "audio")

	folds_train = list(range(1, 11))
	folds_train.remove(fold_val)
	folds_train = tuple(folds_train)
	folds_val = (fold_val,)

	manager = UBS8KDatasetManager(metadata_root, audio_root)

	dataset_train = UBS8KDataset(manager, folds=folds_train, augments=(), cached=False, augment_choser=lambda x: x)
	dataset_train = ToTensorDataset(dataset_train)

	dataset_val = UBS8KDataset(manager, folds=folds_val, augments=(), cached=True, augment_choser=lambda x: x)
	dataset_val = ToTensorDataset(dataset_val)

	datasets = [UBS8KDataset(manager, folds=folds_train, augments=(augm_fn,), cached=False) for augm_fn in augm_list_weak]
	dataset_train_augm_weak = RandomChoiceDataset(datasets)
	dataset_train_augm_weak = ToTensorDataset(dataset_train_augm_weak)

	datasets = [UBS8KDataset(manager, folds=folds_train, augments=(augm_fn,), cached=False) for augm_fn in augm_list_strong]
	dataset_train_augm_strong = RandomChoiceDataset(datasets)
	dataset_train_augm_strong = ToTensorDataset(dataset_train_augm_strong)

	return dataset_train, dataset_val, dataset_train_augm_weak, dataset_train_augm_strong


if __name__ == "__main__":
	main()
