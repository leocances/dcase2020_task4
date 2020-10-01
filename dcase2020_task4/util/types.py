
from typing import Iterable, List, Optional, Sized, Union
from typing_extensions import Protocol


class IterableSized(Iterable, Sized, Protocol):
	"""
		Abstract class for an Iterable and Sized type.
	"""
	pass


def str_to_bool(x: str) -> bool:
	"""
		Convert a string to bool. Case insensitive.
		@param x:
			x in ["true", "1", "yes", "y"] => True
			x in ["false", "0", "no", "n"] => False
			_ => RuntimeError
		@return: The corresponding boolean value.
	"""
	x_low = str(x).lower()
	if x_low in ["true", "1", "yes", "y"]:
		return True
	elif x_low in ["false", "0", "no", "n"]:
		return False
	else:
		raise RuntimeError("Invalid boolean argument \"%s\"." % x)


def str_to_optional_str(x: str) -> Optional[str]:
	"""
		Convert string to optional string value. Case insensitive.
		@param x: Any string value.
		@return: None if x == "None", otherwise the string value.
	"""
	x = str(x)
	if x.lower() == "none":
		return None
	else:
		return x


def str_to_optional_int(x: str) -> Optional[int]:
	"""
		Convert string to optional integer value. Case insensitive.
		@param x: Any string value.
		@return: Integer value, None or throw ValueError exception.
	"""
	x = str(x)
	if x.lower() == "none":
		return None
	else:
		return int(x)


def str_to_optional_float(x: str) -> Optional[float]:
	"""
		Convert string to optional float value. Case insensitive.
		@param x: Any string value.
		@return: Float value, None or throw ValueError exception.
	"""
	x = str(x)
	if x.lower() == "none":
		return None
	else:
		return float(x)


def str_to_union_str_int(x: str) -> Union[str, int]:
	"""
		Convert string to integer value or string value.
		@param x: Any string value.
		@return: If x is digit, return a integer value, otherwise returns a the same string value.
	"""
	x = str(x)
	try:
		x_int = int(x)
		return x_int
	except ValueError:
		return x
