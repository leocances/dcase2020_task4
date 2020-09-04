import numpy as np

from typing import Callable, List, Optional, Tuple, Union


class ConstantEpochUniloss:
	"""
		Activate and deactivate (put 0) 1 hyperparameters in objects with a given constant probability.
		Method "step()" must be called at each epoch end.
	"""

	def __init__(
		self,
		attributes: Union[List[Tuple[object, str]], List[Tuple[object, str, Callable]]],
		ratios_range: List[Tuple[List[float], int, int]],
	):
		"""
			@param attributes: A list of (object to update, attribute name to update, [function to get the current value]).
			@param ratios_range: A list of ratios to determine the behaviour between ranges of epochs.
				Ex : [[0.9, 0.1], 10, 20] =>
					the first object of attributes is activated with a probability of 0.9 between the epochs 10 and 20 and
					the second object is activated with a probability of 0.1 between the epochs 10 and 20.
		"""
		self.attributes = attributes
		self.ratios_range = ratios_range

		self.cur_step = 0
		self.default_value = 0.0

		for i, tuple_ in enumerate(self.attributes):
			if len(tuple_) == 2:
				obj, attr_name = tuple_
				value = obj.__getattribute__(attr_name)
				self.attributes[i] = (obj, attr_name, lambda: value)

		self.reset()

	def reset(self):
		self.cur_step = 0
		self._choose_loss()

	def step(self):
		self.cur_step += 1
		self._choose_loss()

	def _choose_loss(self):
		for ratios, epoch_min, epoch_max in self.ratios_range:
			if epoch_min <= self.cur_step <= epoch_max:
				cur_loss_idx = np.random.choice(range(len(ratios)), p=ratios)

				for i, (obj, attr_name, value_fn) in enumerate(self.attributes):
					new_value = value_fn() if i == cur_loss_idx else self.default_value
					obj.__setattr__(attr_name, new_value)
				break


class WeightLinearUniloss:
	"""
		Increase/decrease linearly the probability to apply a loss hyperparameter.
		The method "step()" must be called at the end of an iteration.
	"""

	def __init__(
		self,
		nb_steps: int,
		targets: Optional[List[Tuple[object, str, float, float, float]]],
		update_idx_on_step: bool = False,
	):
		"""
			@param targets: List of tuples (object to update, attribute name, constant value, probability at start, probability at end)
			@param nb_steps: Nb of steps max. Can be the number of iterations multiply by the number of epochs.
			@param update_idx_on_step: Update the internal index at each step or not.
		"""
		self.targets = targets if targets is not None else []
		self.nb_steps = nb_steps
		self.update_idx_on_step = update_idx_on_step

		self.index_step = 0
		self._update_objects()

	def reset(self):
		self.index_step = 0

	def set_targets(self, targets: Optional[List[Tuple[object, str, float, float, float]]]):
		self.targets = targets if targets is not None else []

	def step(self):
		if self.update_idx_on_step:
			self.index_step += 1
		self._update_objects()

	def get_current_ratios(self) -> List[float]:
		ratios = []
		for _, _, _, ratio_start, ratio_end in self.targets:
			ratio = self.index_step / self.nb_steps * (ratio_end - ratio_start) + ratio_start
			ratios.append(ratio)
		return ratios

	def get_nb_steps(self) -> int:
		return self.nb_steps

	def _update_objects(self):
		ratios = self.get_current_ratios()
		chosen = np.random.choice(range(len(self.targets)), p=ratios)

		for i, (obj, attr_name, value, _, _) in enumerate(self.targets):
			cur_value = value if i == chosen else 0.0
			obj.__setattr__(attr_name, cur_value)


class WeightLinearUnilossStepper:
	def __init__(self, nb_epochs: int, nb_steps_wlu: int, wlu: WeightLinearUniloss):
		self.nb_epochs = nb_epochs
		self.nb_steps_wlu = nb_steps_wlu
		self.wlu = wlu

		self.local_index = 0

	def step(self):
		if self.local_index < self.get_nb_steps_between_probabilities_update():
			self.local_index += 1
		else:
			self.local_index = 0
			self.wlu.index_step += 1

	def get_nb_steps_between_probabilities_update(self) -> int:
		return int(self.nb_epochs / self.nb_steps_wlu)
