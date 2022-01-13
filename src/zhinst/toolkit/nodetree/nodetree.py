"""High level dynamic nodetree for the ziPython package."""

import json
import fnmatch
from keyword import iskeyword as is_keyword
from typing import Dict, Union, Any, Optional, List, Dict, Tuple
# Protocol is available in the typing module since 3.8
try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol
from contextlib import contextmanager
from zhinst.toolkit.nodetree.node import Node

# TODO decide handling of arrays with only one element
# (currently in toolkit these are converted to single nodes)

# TODO waveforms dynamic size


class Connection(Protocol):
    """Protocol class for the connection object used in the nodetree."""

    # pylint: disable=invalid-name
    def listNodesJSON(self, path: str, *args, **kwargs) -> str:
        """Returns a list of nodes with description found at the specified path."""

    def get(self, path: str, *args, **kwargs) -> object:
        """mirrors the behaviour of ziPython get command."""

    def getInt(self, path: str) -> int:
        """mirrors the behaviour of ziPython getInt command."""

    def getDouble(self, path: str) -> float:
        """mirrors the behaviour of ziPython getDouble command."""

    def getString(self, path: str) -> str:
        """mirrors the behaviour of ziPython getDouble command."""

    def set(self, path: str, value: object, **kwargs) -> None:
        """mirrors the behaviour of ziPython set command."""

    def subscribe(self, path: str) -> None:
        """mirrors the behaviour of ziPython subscribe command."""

    def unsubscribe(self, path: str) -> None:
        """mirrors the behaviour of ziPython unsubscribe command."""


class NodeTree:
    """High-level generic node tree for the Zurich Instruments Devices.

    It was designed to used with the zhinst::ziPython module. The ``connection``
    can be an instance of the ``zhinst.ziPython.ziDAQServer`` directly or an
    instance of one of its modules, e.g. ``zhinst.ziPython.ScopeModule``.

    The node tree and its nested elements can be accessed both by attribute and
    by item.
    To speed up the initialisation time the node tree is initialised laszy.
    Meaning the dictionary is kept as a flat dictionary and not converted into
    a nested one. The :class:`Node` returned by the :method:`__getattr__`
    method is only a placeholder. Only when using the `Node` it is
    converted into a real element.

    Args:
        connection: ``zhinst.ziPython.ziDAQServer`` or one of its modules (e.g.
                    ``zhinst.ziPython.ScopeModule``)
        prefix_hide: Prefix, e.g. device id, that should be hidden in the nodetree.
            (Hidden means that users do not need to specify it and it will be added
            automatically to the nodes if necessary)
        list_nodes: list of nodes that should be downloaded from the connection.
            (default = ["*"])
    """

    def __init__(
        self,
        connection: Connection,
        prefix_hide: str = None,
        list_nodes: list = None,
        preloaded_json: dict = None,
    ):
        self._prefix_hide = prefix_hide.lower() if prefix_hide else None
        self._connection = connection
        if not list_nodes:
            list_nodes = ["*"]
        if preloaded_json:
            self._flat_dict = preloaded_json
        else:
            self._flat_dict = {}
            for element in list_nodes:
                nodes_json = self.connection.listNodesJSON(element)
                self._flat_dict = {**self._flat_dict, **json.loads(nodes_json)}
        self._flat_dict = {key.lower(): value for key, value in self._flat_dict.items()}
        self._set_transaction_queue = None
        self._get_transaction_queue = None
        # First Layer must be generate during initialisation to calculate the
        # prefixes to keep
        self._first_layer = None
        self._prefixes_keep = []
        self._generate_first_layer()

    def __getattr__(self, name):
        if not name.startswith("_"):
            return Node(self, (name.lower(),))
        return None

    def __getitem__(self, name):
        name = name.lower()
        if "/" in name:
            name_list = name.split("/")
            if name_list[0]:
                return Node(self, (*name_list,))
            return Node(self, (*name_list[1:],))
        return Node(self, (name,))

    def __contains__(self, k):
        return k.lower() in self._first_layer

    def __dir__(self):
        return self._first_layer

    def __iter__(self):
        for node_raw, info in self._flat_dict.items():
            yield self.raw_path_to_node(node_raw), info

    def _generate_first_layer(self) -> None:
        """Generates the internal ``_first_layer`` list.

        The list represents the available first layer of nested nodes.
        Also create the self._prefixes_keep variable.
        """
        self._first_layer = []
        for raw_node in self._flat_dict:
            if not raw_node.startswith("/"):
                raise SyntaxError(f"{raw_node}: Leading slash not found")
            node_split = raw_node.split("/")
            # Since we always have a leading slash we ignore the first element
            # which is empty.
            if node_split[1] == self._prefix_hide:
                if node_split[2] not in self._first_layer:
                    self._first_layer.append(node_split[2])
            else:
                if node_split[1] not in self._prefixes_keep:
                    self._prefixes_keep.append(node_split[1])
        self._first_layer.extend(self._prefixes_keep)

    def get_node_info(self, node: Union[Node, str]) -> Union[Dict, List[Dict]]:
        """Get the element information from the nodetree

        Unix shell-style wildcards are supported.
        If more than one Node matches the wildcard a list is returned.

        Args:
            node(Union[Node, str]): string representing a node or node object

        Returns:
            dict/list[dict]: node(s) information
        """
        key = (
            self.node_to_raw_path(node)
            if isinstance(node, Node)
            else self.string_to_raw_path(node)
        )
        # resolve potential wildcards
        keys = fnmatch.filter(self._flat_dict.keys(), key)
        if len(keys) == 1:
            result = self._flat_dict.get(keys[0])
        else:
            result = []
            for single_key in keys:
                result.append(self._flat_dict.get(single_key))
        if not result:
            raise KeyError(key)
        return result

    def update_node(
        self, node: Union[Node, str], updates: dict, add: bool = False
    ) -> None:
        """Update Node in the NodeTree

        If the ``key`` argument is a list it will be converted into a string
        representing a node. The conversion adds the ``prefix_hide`` to the
        node string if necessary.
        If the ``key`` does not represent an absolute node (starts with a
        leading slash) it will be converted into one and adds the
        ``prefix_hide`` if necessary.

        Args:
            node(Union[Node, str]): string representing a node or node object
            updates(dict): Entries that will be updated
            add(bool): Add node if it does not exist (default = False)

        Raises:
            KeyError: if node does not exist and the ``add`` Flag is not set
        """
        key = (
            self.node_to_raw_path(node)
            if isinstance(node, Node)
            else self.string_to_raw_path(node)
        )
        # resolve potential wildcards
        keys = fnmatch.filter(self._flat_dict.keys(), key)
        if not keys:
            if not add:
                raise KeyError(key)
            self._flat_dict[key] = updates
        else:
            for single_key in keys:
                self._flat_dict[single_key].update(updates)

    # TODO optimize
    def update_nodes(self, update_dict: dict, add: bool = False) -> None:
        """Update multiple nodes in the NodeTree.

        Similar to update_node but for multiple elements that are represented
        as a dict.

        Args:
            update_dict(dict): dict with node as keys and Entries that will be
                updated as values.
            add(bool): Add node if it does not exist (default = False)

        Raises:
            KeyError: if node does not exist and the ``add`` Flag is not set
        """
        for node, updates in update_dict.items():
            self.update_node(node, updates, add=add)

    def raw_path_to_node(self, raw_path: str) -> Node:
        """Converts a raw node path string into a Node object.

        Args:
            raw_path (str): Raw node path (e.g. /dev1234/relative/path/to/node).

        Returns:
            Node: The corresponding Node object linked to this nodetree.
        """
        node_split = raw_path.split("/")
        # buildin keywords are escaped with a tailing underscore
        # (https://pep8.org/#descriptive-naming-styles)
        node_split = [node + "_" if is_keyword(node) else node for node in node_split]
        # Since we always have a leading slash we ignore the first element
        # which is empty.
        if node_split[1] == self._prefix_hide:
            return Node(self, (*node_split[2:],))
        return Node(self, (*node_split[1:],))

    def node_to_raw_path(self, node: Node) -> str:
        """Converts a node into a raw node path string.

        The conversion adds the ``prefix_hide`` to the node string if necessary.

        Args:
            node_tuple (tuple[str]): tuple of strings representing the node

        Returns:
            str: node/key of the tuple in the internal dictionary
        """
        # buildin keywords are escaped with a tailing underscore
        # (https://pep8.org/#descriptive-naming-styles)
        node_list = [element.rstrip("_") for element in node.raw_tree]
        if not node_list:
            return "/"
        if node_list[0] in self._prefixes_keep:
            string_list = "/".join(node_list)
        else:
            string_list = "/".join([self._prefix_hide] + node_list)
        string_list.replace("_", "")
        return "/" + string_list

    def string_to_raw_path(self, node_string: str) -> str:
        """Converts a string into a raw node path string.

        If the string does not represent a absolute path (leading slash) the
        ``prefix_hide`` will be added to the node string if necessary.

        Args:
            node_string (str):  string representation of the node

        Returns:
            str: node/key of the tuple in the internal dictionary
        """
        if not node_string.startswith("/") and self._prefix_hide:
            insert_prefix = True
            for keep_prefix in self._prefixes_keep:
                if node_string.startswith(keep_prefix):
                    insert_prefix = False
                    break
                if node_string.startswith(self._prefix_hide):
                    raise ValueError(
                        f"{node_string} is a relative path but should be a "
                        "absolute path (leading slash)"
                    )
            return (
                "/" + self._prefix_hide + "/" + node_string
                if insert_prefix
                else "/" + node_string
            )
        return node_string

    @contextmanager
    def set_transaction(self) -> None:
        """Context manager for a transactional set.

        Can be used as a conext in a with statement and bundles all node set
        commands into a single transaction. This reduces the network overhead
        and often increases the speed.

        WARNING: ziVectorData are not supported in a transactional set and will
        cause a AttributeError.

        Within the with block a set commands to a node will be buffered
        and bundeld into a single command at the end automatically.
        (All other opperations, e.g. getting the value of a node, will not be
        affected)

        WARNING: The set is always perfromed as deep set if called on device nodes.

        Examples:
            >>> with nodetree.set_transaction():
                    nodetree.test[0].a(1)
                    nodetree.test[1].a(2)
        """
        self._set_transaction_queue = []
        try:
            yield
            nodes_raw = []
            for item in self._set_transaction_queue:
                try:
                    nodes_raw.append((self.node_to_raw_path(item[0]), item[1]))
                except AttributeError:
                    nodes_raw.append((self.string_to_raw_path(item[0]), item[1]))
            self.connection.set(nodes_raw)
        finally:
            self._set_transaction_queue = None

    def add_to_set_transaction(self, node: Union[Node, str], value: Any) -> None:
        """Adds a single node set command to the set transaction.

        Args:
            node (Union[Node,str]): node
            value (Any): Value that should be set to the node
        Raises:
            AttributeError: if no transaction is in progress
        """
        try:
            self._set_transaction_queue.append((node, value))
        except AttributeError as exception:
            raise AttributeError("No set transaction is in progress.") from exception

    @property
    def set_transaction_queue(self) -> Optional[List[Tuple]]:
        """Queued set commands for a set transaction

        If no transaction is in progress the queue is of type None.

        Returns:
            List[Tuple]: List of the set commands in the internal queue
        """
        return self._set_transaction_queue

    @property
    def connection(self) -> Connection:
        """Underlying connection to the instrument."""
        return self._connection

    @property
    def prefix_hide(self) -> str:
        """Prefix, e.g. device id, that is hidden in the nodetree.

        Hidden means that users do not need to specify it and it will be added
        automatically to the nodes if necessary.
        """
        return self._prefix_hide

    @property
    def raw_dict(self) -> dict:
        return self._flat_dict
