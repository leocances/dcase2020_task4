import numpy as np

from dcase2020.augmentation_utils.augmentations import ImgAugmentation


class ImgRGBAugmentation(ImgAugmentation):
	""" Abstract class for images augmentations of size (3, width, height). """

	def __init__(self, ratio: float, value_range: list = (0, 255)):
		super().__init__(ratio)
		self.value_range = value_range

	def _apply(self, data):
		if len(data.shape) != 3 or data.shape[0] != 3:
			raise RuntimeError(
				"Invalid dimension %s. This augmentation only supports RGB (3, width, height) images." %
				str(data.shape)
			)
		return self.apply_helper(data)

	def apply_helper(self, data):
		raise NotImplementedError("Abstract method")


class Gray(ImgRGBAugmentation):
	def __init__(self, ratio: float = 1.0):
		super().__init__(ratio)

	def apply_helper(self, data):
		gray_img = np.mean(data, 0)
		for i in range(data.shape[0]):
			data[i] = gray_img.copy()

		return data


class RandCrop(ImgRGBAugmentation):
	def __init__(self, ratio: float = 1.0, rect_min_scale: tuple = (0.1, 0.1), rect_max_scale: tuple = (0.5, 0.5)):
		super().__init__(ratio)
		self.rect_min_scale = rect_min_scale
		self.rect_max_scale = rect_max_scale

	def apply_helper(self, data):
		width, height = data.shape[1], data.shape[2]
		r_width = np.random.randint(max(1, self.rect_min_scale[0] * width), max(2, self.rect_max_scale[0] * width))
		r_height = np.random.randint(max(1, self.rect_min_scale[1] * height), max(2, self.rect_max_scale[1] * height))

		r_left = np.random.randint(0, width - r_width)
		r_top = np.random.randint(0, height - r_height)
		r_right = r_left + r_width
		r_down = r_top + r_height

		for i in range(data.shape[0]):
			data[i, r_left:r_right, r_top:r_down] = (self.value_range[1] - self.value_range[0]) / 2.0

		return data


class Unicolor(ImgRGBAugmentation):
	def __init__(self, ratio: float = 1.0):
		super().__init__(ratio)

	def apply_helper(self, data):
		max_img = np.max(data, 0)

		color_chosen = np.random.randint(data.shape[0])
		for i in range(data.shape[0]):
			if i != color_chosen:
				data[i] = self.value_range[0]
			else:
				data[i] = max_img

		return data


class Inversion(ImgRGBAugmentation):
	def __init__(self, ratio: float = 1.0):
		super().__init__(ratio)

	def apply_helper(self, data):
		return self.value_range[1] - data