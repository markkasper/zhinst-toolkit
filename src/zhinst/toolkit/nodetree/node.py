"""Single lazy node of a :class:'Nodetree'."""

import re
import time
import warnings
import fnmatch
from collections import OrderedDict
from typing import Any, Callable, Set, Dict, Tuple
from functools import lru_cache

def lazy_property(property_function:Callable):
    """Alternative for functools.cached_property.

    functools.cached_property is only available since python 3.8.
    Should be replaced with functools.cached_property once no version below
    python 3.8 is supported.

    Args:
        property_function (Callable): property function

    Returns
        Any: Retun value of the property function

    """
    return property(lru_cache()(property_function))

class Node:
    """lazy node of a :class:'Nodetree'.

    The node is implemented in a lazy way. Meaning unless operations ar performed
    on the node no checks wether the node is valid or not are performed.
    Every node overwrites the __getattr__ and __getitem__ in the same way the
    root (:class:'Nodetree') does. Meaning nodes can be chained.

    TODO go into detail.

    Args:
        root (nodetree.NodeTree): root of the nodetree
        tree (tuple): tree (node path as tuple) of the current node
    """

    def __init__(self, root: "NodeTree", tree: tuple):
        self._root = root
        self._tree = tree
        self._dir_info = None

    def __getattr__(self, name):
        if not name.startswith("_"):
            return Node(self._root, self._tree + (name,))
        return None

    def __getitem__(self, name):
        return Node(self._root, self._tree + (str(name),))

    def __contains__(self, k):
        return k in self._next_layer

    def __iter__(self):
        own_node_raw = self.node
        for node_raw, info in self._root.raw_dict.items():
            if own_node_raw in node_raw:
                yield self._root.raw_path_to_node(node_raw), info

    def __repr__(self):
        return self.node

    def __call__(
        self, value: Any = None, deep=False, enum=True, parse=True, **kwargs
    ) -> Any:
        """get or set the value of the node.

        If the node is a partial node, meaning it represents a subset of multiple
        other nodes a this function will return a dictionary with the values of
        all child nodes.

        The additional kwargs will be forwarded to the maped ziPython function call.

        Args:
        value (Any): Value that should be set to the node. If None the value of the
            node will be returned. (default = None)
        deep (bool): Flag if the set operation should be blocking until the data
            has arrived at the device, respectively if the get operation should return
            the value from the device or the cached value on the data server. If this
            flag is set the opperation takes significantly longer. (default = False)
        enum (bool): Flag if enumerated values should accept/return the enum value as
            string. (default = True)
        parse (bool): Flag if the SetParser/GetParser from the Node, if present, should
            be applied or not. (default = True)
        """
        if value is None:
            return self._get(deep=deep, enum=enum, parse=parse, **kwargs)
        return self._set(value, deep=deep, enum=enum, parse=parse, **kwargs)

    def __dir__(self):
        if not self._dir_info:
            self._dir_info = self._next_layer.copy()
            if len(self._next_layer) > 0 and next(iter(self._next_layer)).isdecimal():
                # TODO decide what should happen self is a list
                self._dir_info = {attr for attr in dir([]) if not attr.startswith("_")}
            else:
                for var, value in vars(self.__class__).items():
                    if isinstance(value, property) and not var.startswith("_"):
                        self._dir_info.add(var)
            self._dir_info = sorted(self._dir_info)
        return self._dir_info

    def __eq__(self, other):
        # buildin keywords are escaped with a tailing underscore
        # (https://pep8.org/#descriptive-naming-styles)
        own_node_list = tuple(node.rstrip("_") for node in self._tree)
        other_node_list = tuple(node.rstrip("_") for node in other.raw_tree)
        return own_node_list == other_node_list and self._root is other._root

    def __hash__(self):
        own_node_list = tuple(node.rstrip("_") for node in self._tree)
        if not own_node_list:
            try:
                own_node_list = repr(self)
            except RecursionError:
                own_node_list = "Node"
        return hash((own_node_list, repr(self._root)))

    @lazy_property
    def _next_layer(self) -> Set[str]:
        """List of direct child nodes"""
        next_layer = set()
        for node, _ in self._root:
            if self._is_child_node(node):
                next_layer.add(node.raw_tree[len(self._tree)])
        return next_layer

    @lazy_property
    def _node_information(self) -> dict:
        """detailed information about the node."""
        if any(wildcard in "".join(self._tree) for wildcard in ["*", "?", "["]):
            raise KeyError(self._root.node_to_raw_path(self))
        return self._root.get_node_info(self)

    @lazy_property
    def _option_map(self) -> dict:
        """Map to map options to the respective values."""
        option_map = {}
        for key, value in self.options.items():
            options = re.findall(r'"(.+?)"[,:]+', value)
            option_map.update({x: int(key) for x in options})
        return option_map

    @lazy_property
    def _option_map_reverse(self) -> dict:
        """Map to map values to the respective option."""
        option_map_reverse = {}
        for key, value in self.options.items():
            options = re.findall(r'"(.+?)"[,:]+', value)
            if len(options) > 0:
                option_map_reverse[int(key)] = options[0]
        return option_map_reverse

    def _contains_wildcards(self) -> bool:
        """Does the node contain any wildcard symbols

        Supported wildcards are *,?,[

        Returns:
            bool: Flag if the node contains wildcards
        """
        return any(wildcard in "".join(self._tree) for wildcard in ["*", "?", "["])

    def _get(self, deep=False, enum=True, parse=True, **kwargs) -> Any:
        """get the value from the node.

        The kwargs will be forwarded to the maped ziPython function call

        Args:
            deep (bool): Flag if the get operation should return the cached value
                from the dataserver or get the value from the device, which is
                significantly slower.
            enum (bool): Flag if enumerated values should return the enum value
                as string or return the raw number
            parse (bool): Flag if the GetParser, if present, should be applied or not.
        """
        try:
            if "Read" not in self.properties:
                raise AttributeError(f"{str(self)} is not readable!")
        except KeyError:
            if self._contains_wildcards():
                return self._get_wildcard(self._root.node_to_raw_path(self), **kwargs)
            # If node is a partial node excecute a wildcard get
            if self.is_partial_node:
                return self._get_wildcard(
                    self._root.node_to_raw_path(self) + "/*", **kwargs
                )
            raise
        timestamp = None
        value = None
        if deep:
            timestamp, value = self._get_deep(**kwargs)
        else:
            value = self._get_cached(**kwargs)
        if enum and "Options" in self._node_information:
            mapped_value = self._option_map_reverse.get(value)
            value = mapped_value if mapped_value else value
        if parse:
            get_parser = self._node_information.get("GetParser")
            value = get_parser(value) if callable(get_parser) else value
        return (timestamp, value) if timestamp else value

    def _get_wildcard(self, node_raw, **kwargs) -> dict:
        """execute a wildcard get.

        The get is performed as a deep get and therefor contains the timestamp
        (for all devices except HF2)

        WARNING: only works for partial nodes

        The kwargs will be forwarded to the maped ziPython function call.

        Returns:
            dict: dictiononary with the value of all subnodes
        """
        if "flat" not in kwargs:
            kwargs["flat"] = True
        result_raw = self._root.connection.get(node_raw, **kwargs)
        if not result_raw:
            raise KeyError(node_raw)
        if not kwargs["flat"]:
            return result_raw
        try:
            return {
                self._root.raw_path_to_node(node_raw): (
                    node_value["timestamp"][0],
                    node_value["value"][0],
                )
                for node_raw, node_value in result_raw.items()
            }
        except IndexError:
            # HF2 has not timestamp
            return {
                self._root.raw_path_to_node(node_raw): (None, node_value[0])
                for node_raw, node_value in result_raw.items()
            }

    def _get_deep(self, **kwargs) -> Tuple[int, Any]:
        """get the node value from the device.

        The kwargs will be forwarded to the maped ziPython function call.

        Note: The HF2 does not support the timestamp option and will therfore
        return None for the timestamp.

        Returns:
            Tuple[int, Any]: (timestamp, value)
        """
        value = None
        timestamp = None
        if "settingsonly" not in kwargs:
            kwargs["settingsonly"] = False
        if "flat" not in kwargs:
            kwargs["flat"] = True
        raw_value = self._root.connection.get(self.node, **kwargs)
        if isinstance(raw_value, OrderedDict):
            if not raw_value:
                raise TypeError(
                    "keyword 'deep' is not available for this node. "
                    "(e.g. node is a sample node)"
                )
            try:
                value = list(raw_value.values())[0]["value"][0]
                timestamp = list(raw_value.values())[0]["timestamp"][0]
            except TypeError:
                # ZIVectorData have a different structure
                value = list(raw_value.values())[0][0]["vector"]
                timestamp = list(raw_value.values())[0][0]["timestamp"]
            except IndexError:
                # HF2 has not timestamp
                value = list(raw_value.values())[0][0]

        return (timestamp, value)

    def _get_cached(self, **kwargs) -> Any:
        """get the cached node value from the data server.

        The kwargs will be forwarded to the maped ziPython function call.

        Returns:
            Any: chached node value from the data server
        """
        if "Integer" in self.type:
            value = self._root.connection.getInt(self.node)
        elif self.type == "Complex Double":
            get_complex_op = getattr(self._root.connection, "getComplex", None)
            if not get_complex_op:
                raise AttributeError("connection object has no attribute 'getComplex'")
            value = get_complex_op(self.node, **kwargs)
        elif self.type == "Double":
            value = self._root.connection.getDouble(self.node)
        elif self.type == "String":
            value = self._root.connection.getString(self.node)
        elif self.type == "ZIVectorData":
            _, value = self._get_deep(**kwargs)
        elif self.type == "ZIDemodSample":
            sample_op = getattr(self._root.connection, "getSample", None)
            if not callable(sample_op):
                raise AttributeError("connection does not support getSample")
            value = sample_op(self.node, **kwargs)
        elif self.type == "ZIDIOSample":
            dio_get_op = getattr(self._root.connection, "getDIO", None)
            try:
                value = dio_get_op(self.node, **kwargs)
            except TypeError:
                raise RuntimeError(f"nodes of type {self.type} can only be polled.")
        else:
            # ZIPWAWave, ZIDemodSample, ZITriggerSample, ZICntSample,
            # ZIImpedanceSample, ZIScopeWave, ZIAuxInSample
            # TODO find solution
            raise RuntimeError(f"nodes of type {self.type} can only be polled.")
        return value

    def _set(self, value: Any, deep=False, enum=True, parse=True, **kwargs) -> None:
        """set the value to the node.

        The kwargs will be forwarded to the maped ziPython function call.

        Args:
            value (Any): value
            deep (bool): Flag if the set operation should be blocking until the data
                has arrived at the device. (default=False)
            enum (bool): Flag if enumerated values should accept the enum value as
                string. (default=True)
            parse (bool): Flag if the SetParser, if present, should be applied or not.
                (default=True)
        """
        try:
            if "Write" not in self.properties:
                raise AttributeError("This parameter is read-only.")
        except KeyError:
            if self._contains_wildcards():
                return self._set_wildcard(value, **kwargs)
        if parse:
            set_parser = self._node_information.get("SetParser")
            value = set_parser(value) if callable(set_parser) else value
        if enum and "Options" in self._node_information:
            mapped_value = self._option_map.get(value)
            value = mapped_value if mapped_value is not None else value
        if self._root.set_transaction_queue is not None:
            if self.type == "ZIVectorData":
                raise AttributeError("Transactions do not support ZIVectorData")
            self._root.add_to_set_transaction(self, value)
        elif self.type == "ZIVectorData":
            vector_set_op = getattr(self._root.connection, "setVector", None)
            if not callable(vector_set_op):
                raise AttributeError("connection does not support setVector")
            vector_set_op(self.node, value, **kwargs)
        elif deep:
            self._set_deep(value, **kwargs)
        else:
            self._root.connection.set(self.node, value, **kwargs)

    def _set_wildcard(self, value:Any, **kwargs) -> None:
        """Performs a transactional set on all nodes that match the wildcard.

        The kwargs will be forwarded to the mapped ziPython function call.

        Args:
            value (Any): value

        Raises:
            KeyError: if the wildcard does not resolve to a valid node
        """
        nodes_raw = fnmatch.filter(
                self._root.raw_dict.keys(), self._root.node_to_raw_path(self)
            )
        if not nodes_raw:
            raise KeyError(self._root.node_to_raw_path(self))
        with self._root.set_transaction():
            for node_raw in nodes_raw:
                self._root.raw_path_to_node(node_raw)(value)

    def _set_deep(self, value: Any, **kwargs) -> None:
        """set the node value from device.

        The kwargs will be forwarded to the mapped ziPython function call.

        Args:
            value (Any): value

        Raises:
            RuntimeError: if deep get is not possible
        """
        if isinstance(value, int):
            sync_set_op = getattr(self._root.connection, "syncSetInt", None)
        elif isinstance(value, float):
            sync_set_op = getattr(self._root.connection, "syncSetDouble", None)
        elif isinstance(value, str):
            sync_set_op = getattr(self._root.connection, "syncSetString", None)
        else:
            raise RuntimeError(
                f"Invalid type {type(value)} for deep set "
                "(only int,float and str are supported)"
            )
        try:
            sync_set_op(self.node, value, **kwargs)
        except TypeError:
            warnings.warn(
                "deep set is not supported for this connection.\n"
                "(this likely cause because the connection is a module and a deep "
                "set does not make sense there.)\n"
                "The set is executed a normal set instead",
                RuntimeWarning,
                stacklevel=3,
            )
            self._root.connection.set(self.node, value, **kwargs)

    def _is_child_node(self, child_node: "Node") -> bool:
        """Checks if a node is child node of this node.

        Args:
            child_node (Node): potential child node

        Returns:
            bool: Flag if passed node is a child_node
        """
        if len(child_node.raw_tree) <= len(self._tree):
            # No need to proceed if potential child node is shorter or equaly
            # long than the node itself
            return False
        for key, child_key in zip(self._tree, child_node.raw_tree):
            if str(key) != str(child_key):
                return False
        return True

    def wait_for_state_change(
        self,
        value: int,
        timeout: float = 2,
        sleep_time: float = 0.005,
    ) -> bool:
        """Waits until the node has the expected state/value.

        WARNING: Only supports integer values as reference.

        Args:
            value (int): expected value of the node.
            timeout (float): max wait time. (default = 2)
            sleep_time (float): sleep interval in seconds. (default = 0.006)

        Returns:
            bool: Flag if the value/state of the node has the expected value.
        """
        try:
            if "Options" in self._node_information and isinstance(value, int):
                value = self._option_map_reverse.get(value)
            start_time = time.time()
            while start_time + timeout >= time.time() and self._get() != value:
                time.sleep(sleep_time)
            return self._get() == value
        except KeyError:
            if self._contains_wildcards():
                nodes_raw = fnmatch.filter(
                    self._root.raw_dict.keys(), self._root.node_to_raw_path(self)
                )
                results = []
                for node_raw in nodes_raw:
                    node = self._root.raw_path_to_node(node_raw)
                    results.append(
                        node.wait_for_state_change(
                            value, timeout=timeout, sleep_time=sleep_time
                        )
                    )
                    # After the first node has been checked the other nodes do
                    # not need to wait again
                    timeout = 0
                if results:
                    return results
            raise

    def subscribe(self) -> None:
        """Subscribe to nodes. Fetch data with the poll command.

        In order to avoid fetching old data that is still in the buffer execute
        a flush command before subscribing to data streams.
        """
        self._root.connection.subscribe(self.node)

    def unsubscribe(self) -> None:
        """Unsubscribe data stream.

        Use this command after recording to avoid buffer overflows that may
        increase the latency of other command.
        """
        self._root.connection.unsubscribe(self.node)

    @property
    def node(self) -> str:
        """LabOne representation of the node."""
        try:
            return self._node_information.get("Node", "")
        except KeyError as key_error:
            return key_error.args[0]

    @property
    def description(self) -> str:
        """Description of the node."""
        return self._node_information.get("Description", "")

    @property
    def type(self) -> str:
        """Type of the node."""
        return self._node_information.get("Type", "")

    @property
    def unit(self) -> str:
        """Unit of the node."""
        return self._node_information.get("Unit", "")

    @property
    def options(self) -> Dict[int, str]:
        """Options of the node."""
        return self._node_information.get("Options", {})

    @property
    def properties(self) -> str:
        """Properties of the node."""
        return self._node_information.get("Properties", "")

    @property
    def raw_tree(self) -> list:
        """Internal representation of the node."""
        return self._tree

    @property
    def root(self) -> 'NodeTree':
        return self._root

    @lazy_property
    def is_partial_node(self) -> bool:
        """Flag if the node is a partial node"""
        is_partial_node = False
        for node, _ in self._root:
            if self._is_child_node(node):
                is_partial_node = True
                break
        return is_partial_node
