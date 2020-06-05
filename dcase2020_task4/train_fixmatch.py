
from easydict import EasyDict as edict
from torch.nn import Module
from torch.optim import SGD
from torch.utils.data import DataLoader
from typing import Callable, Dict

from dcase2020.pytorch_metrics.metrics import Metrics

from dcase2020_task4.fixmatch.cosine_scheduler import CosineLRScheduler
from dcase2020_task4.fixmatch.loss import FixMatchLoss
from dcase2020_task4.fixmatch.trainer import FixMatchTrainer
from dcase2020_task4.util.utils_match import build_writer
from dcase2020_task4.learner import DefaultLearner
from dcase2020_task4.validator import DefaultValidator


def train_fixmatch(
	model: Module,
	acti_fn: Callable,
	loader_train_s_weak: DataLoader,
	loader_train_u_weak_strong: DataLoader,
	loader_val: DataLoader,
	metric_s: Metrics,
	metric_u: Metrics,
	metrics_val: Dict[str, Metrics],
	hparams: edict,
):

	optim = SGD(model.parameters(), lr=hparams.lr, weight_decay=hparams.weight_decay)
	scheduler = CosineLRScheduler(optim, nb_epochs=hparams.nb_epochs, lr0=hparams.lr)

	hparams.train_name = "FixMatch"
	writer = build_writer(hparams)

	criterion = FixMatchLoss.from_edict(hparams)
	trainer = FixMatchTrainer(
		model, acti_fn, optim, loader_train_s_weak, loader_train_u_weak_strong, metric_s, metric_u,
		writer, criterion, hparams.mode, hparams.threshold_multihot
	)
	validator = DefaultValidator(
		model, acti_fn, loader_val, metrics_val, writer
	)
	learner = DefaultLearner(hparams.train_name, trainer, validator, hparams.nb_epochs, scheduler)
	learner.start()

	writer.add_hparams(hparam_dict=dict(hparams), metric_dict={})
	writer.close()


def default_fixmatch_hparams() -> edict:
	hparams = edict()
	hparams.lambda_u = 1.0
	hparams.beta = 0.9  # used only for SGD
	hparams.threshold_mask = 0.95  # tau
	hparams.threshold_multihot = 0.5  # tau
	# hparams.batch_size = 16  # in paper: 64
	hparams.lr = 0.03  # learning rate, eta
	hparams.weight_decay = 1e-4
	return hparams