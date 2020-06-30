import torch

from torch.nn import Module
from torch.optim.optimizer import Optimizer
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
from typing import Callable, Dict, List, Optional

from metric_utils.metrics import Metrics

from dcase2020_task4.fixmatch.losses.abc import FixMatchLossTagABC
from dcase2020_task4.metrics_recorder import MetricsRecorder
from dcase2020_task4.trainer_abc import SSTrainerABC
from dcase2020_task4.util.ramp_up import RampUp
from dcase2020_task4.util.utils_match import binarize_onehot_labels, get_lr
from dcase2020_task4.util.zip_cycle import ZipCycle


class FixMatchTrainer(SSTrainerABC):
	def __init__(
		self,
		model: Module,
		acti_fn: Callable,
		optim: Optimizer,
		loader_train_s_augm_weak: DataLoader,
		loader_train_u_augms_weak_strong: DataLoader,
		metrics_s: Dict[str, Metrics],
		metrics_u: Dict[str, Metrics],
		criterion: FixMatchLossTagABC,
		writer: Optional[SummaryWriter],
		mode: str,
		rampup_lambda_u: Optional[RampUp],
		threshold_multihot: Optional[float] = None,
	):
		self.model = model
		self.acti_fn = acti_fn
		self.optim = optim
		self.loader_train_s_augm_weak = loader_train_s_augm_weak
		self.loader_train_u_augms_weak_strong = loader_train_u_augms_weak_strong
		self.metrics_s = metrics_s
		self.metrics_u = metrics_u
		self.criterion = criterion
		self.writer = writer
		self.mode = mode
		self.rampup_lambda_u = rampup_lambda_u
		self.threshold_multihot = threshold_multihot

		self.metrics_recorder = MetricsRecorder(
			"train/",
			list(self.metrics_s.keys()) +
			list(self.metrics_u.keys()) +
			["loss", "loss_s", "loss_u"]
		)

		if self.mode == "multihot" and self.threshold_multihot is None:
			raise RuntimeError("Multihot threshold cannot be None in multihot mode.")

	def train(self, epoch: int):
		self.reset_all_metrics()
		self.metrics_recorder.reset_epoch()
		self.model.train()

		loaders_zip = ZipCycle([self.loader_train_s_augm_weak, self.loader_train_u_augms_weak_strong])
		iter_train = iter(loaders_zip)

		for i, item in enumerate(iter_train):
			(s_batch_augm_weak, s_labels), (u_batch_augm_weak, u_batch_augm_strong) = item

			s_batch_augm_weak = s_batch_augm_weak.cuda().float()
			s_labels = s_labels.cuda().float()
			u_batch_augm_weak = u_batch_augm_weak.cuda().float()
			u_batch_augm_strong = u_batch_augm_strong.cuda().float()

			# Compute logits
			s_logits_augm_weak = self.model(s_batch_augm_weak)
			u_logits_augm_strong = self.model(u_batch_augm_strong)

			s_pred_augm_weak = self.acti_fn(s_logits_augm_weak, dim=1)
			u_pred_augm_strong = self.acti_fn(u_logits_augm_strong, dim=1)

			# Use guess u label with prediction of weak augmentation of u
			with torch.no_grad():
				u_logits_augm_weak = self.model(u_batch_augm_weak)
				u_pred_augm_weak = self.acti_fn(u_logits_augm_weak, dim=1)
				if self.mode == "onehot":
					u_labels_weak_guessed = binarize_onehot_labels(u_pred_augm_weak)
				elif self.mode == "multihot":
					u_labels_weak_guessed = (u_pred_augm_weak > self.threshold_multihot).float()
				else:
					raise RuntimeError("Invalid argument \"mode = %s\". Use %s." % (self.mode, " or ".join(("onehot", "multihot"))))

			# Update model
			loss, loss_s, loss_u = self.criterion(
				s_pred_augm_weak, s_labels, u_pred_augm_weak, u_pred_augm_strong, u_labels_weak_guessed)

			self.optim.zero_grad()
			loss.backward()
			self.optim.step()

			# Compute metrics
			with torch.no_grad():
				if self.rampup_lambda_u is not None:
					self.criterion.lambda_u = self.rampup_lambda_u.value()
					self.rampup_lambda_u.step()

				self.metrics_recorder.add_value("loss", loss.item())
				self.metrics_recorder.add_value("loss_s", loss_s.item())
				self.metrics_recorder.add_value("loss_u", loss_u.item())

				metrics_preds_labels = [
					(self.metrics_s, s_pred_augm_weak, s_labels),
					(self.metrics_u, u_pred_augm_strong, u_labels_weak_guessed),
				]
				self.metrics_recorder.apply_metrics_and_add(metrics_preds_labels)
				self.metrics_recorder.print_metrics(epoch, i, len(loaders_zip))

		print("")

		if self.writer is not None:
			self.writer.add_scalar("hparams/lr", get_lr(self.optim), epoch)
			self.writer.add_scalar("hparams/lambda_u", self.criterion.lambda_u, epoch)
			self.metrics_recorder.store_in_writer(self.writer, epoch)

	def nb_examples_supervised(self) -> int:
		return len(self.loader_train_s_augm_weak) * self.loader_train_s_augm_weak.batch_size

	def nb_examples_unsupervised(self) -> int:
		return len(self.loader_train_u_augms_weak_strong) * self.loader_train_u_augms_weak_strong.batch_size

	def get_all_metrics(self) -> List[Dict[str, Metrics]]:
		return [self.metrics_s, self.metrics_u]
