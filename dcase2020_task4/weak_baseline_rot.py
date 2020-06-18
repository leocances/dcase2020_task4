
from torch import nn, Tensor
from dcase2020_task4.baseline.models import WeakBaseline, WeakStrongBaseline


class WeakBaselineRot(WeakBaseline):
	def __init__(self, nb_rot: int = 4):
		super().__init__()
		nb_classes = 10

		self.classifier_rot = nn.Sequential(
			nn.Flatten(),
			nn.Linear(1696, nb_rot)
		)
		self.classifier_count = nn.Sequential(
			nn.Flatten(),
			nn.Linear(1696, nb_classes + 1)
		)

	def forward_rot(self, x: Tensor) -> Tensor:
		# Fox ReMixMatch
		x = x.view(-1, 1, *x.shape[1:])

		x = self.features(x)
		x = self.classifier_rot(x)

		return x

	def forward_count(self, x: Tensor) -> Tensor:
		# For FixMatch V4 tag only
		x = x.view(-1, 1, *x.shape[1:])

		x = self.features(x)
		x = self.classifier_count(x)

		return x


class WeakStrongBaselineRot(WeakStrongBaseline):
	def __init__(self, nb_rot: int = 4):
		super().__init__()

		self.classifier_rot = nn.Sequential(
			nn.Flatten(),
			nn.Linear(1696, nb_rot)
		)

	def forward_rot(self, x: Tensor) -> Tensor:
		# Fox ReMixMatch
		x = x.view(-1, 1, *x.shape[1:])

		x = self.features(x)
		x = self.classifier_rot(x)

		return x
