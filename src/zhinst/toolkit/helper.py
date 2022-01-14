"""Helper functions used in toolkit"""
from functools import lru_cache
from typing import Callable, Any
from collections.abc import Sequence
from zhinst.toolkit.nodetree import NodeTree, Node

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


class NodeList(Sequence, Node):
    """List of nodelike Objects

    List oft preinitialized Classes that intherit from the Node class would not
    support wildcards since they would be of type list.
    This class holds the preinitialized Objects. But if a the passed item is not
    an interger it returns a Node instead.

    Args:
        elements (Any): preinitialized child elements
        root (NodeTree): root of the nodetree
        tree (tuple): tree (node path as tuple) of the current node
    """
    def __init__(self, elements:Any, root:NodeTree, tree:tuple):
        Sequence.__init__(self)
        Node.__init__(self, root, tree)
        self._elements = elements

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._elements[item]
        return Node(self._root, self._tree + (str(item),))

    def __len__(self):
        return len(self._elements)

