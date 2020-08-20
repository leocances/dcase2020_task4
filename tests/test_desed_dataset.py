import json
import os.path as osp

from argparse import ArgumentParser, Namespace

from augmentation_utils.signal_augmentations import TimeStretch
from dcase2020.datasetManager import DESEDManager
from dcase2020.datasets import DESEDDataset


def create_args() -> Namespace:
	parser = ArgumentParser()
	parser.add_argument("--dataset_path", type=str, default="/projets/samova/leocances/dcase2020/DESED/")
	return parser.parse_args()


def test():
	args = create_args()
	desed_metadata_root = osp.join(args.dataset_path, "dataset", "metadata")
	desed_audio_root = osp.join(args.dataset_path, "dataset", "audio")

	manager = DESEDManager(
		desed_metadata_root, desed_audio_root,
		from_disk=False,
		sampling_rate=22050,
		verbose=1
	)

	# manager.add_subset("weak")
	manager.add_subset("synthetic20")
	# manager.add_subset("unlabel_in_domain")

	augments = ()  # (TimeStretch(1.0),)
	dataset = DESEDDataset(manager, train=True, val=False, augments=augments, cached=False, weak=True, strong=True)

	print("len : ", len(dataset))  # weak = 11808, synthetic20 = 2584

	print("Strong sizes : ")
	idx = 0
	x, y = dataset[idx]
	print("x = ", x.shape)  # (64, 431)
	print("y[0] = ", y[0].shape)  # (10,)
	print("y[1] = ", y[1].shape)  # (10, 431)

	data = {"x": x.tolist(), "y_weak": y[0].tolist(), "y_strong": y[1].tolist(), "index": idx}
	with open("spec_time_stretch.json", "w") as file:
		json.dump(data, file, indent="\t")


def test_signal_spec():
	args = create_args()
	desed_metadata_root = osp.join(args.dataset_path, "dataset", "metadata")
	desed_audio_root = osp.join(args.dataset_path, "dataset", "audio")

	manager = DESEDManager(
		desed_metadata_root, desed_audio_root,
		from_disk=True,
		sampling_rate=22050,
		verbose=1
	)

	manager.add_subset("weak")
	manager.add_subset("synthetic20")
	dataset = DESEDDataset(manager, train=True, val=False, augments=(), cached=False, weak=True, strong=True)

	idx = 0
	filename = dataset.filenames[idx]
	signal = dataset.get_raw_audio(filename)
	spec, labels = dataset[idx]

	data = {
		"idx": idx,
		"signal": signal.tolist(),
		"spec": spec.tolist(),
		"labels": [label.tolist() for label in labels],
	}
	with open("signal_spec.json", "w") as file:
		json.dump(data, file, indent="\t")


if __name__ == "__main__":
	test_signal_spec()
