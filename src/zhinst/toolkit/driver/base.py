# Copyright (C) 2021 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

""" Zurich Instruments Toolkit (zhinst-toolkit) Base Instrument Driver.

This driver provides a high-level controller for the all Zurich Instrument
devices for Zurich Instruments Toolkit (zhinst-toolkit). It is based on
the LabOne Python API ziPython and forms the basis for instrument drivers used
in QCoDeS and Labber.
"""
import re
from pathlib import Path
import json
import copy
import logging
from zhinst.toolkit.nodetree import NodeTree, Node
from zhinst.toolkit.driver.parsers import node_parser

logger = logging.getLogger(__name__)

class BaseInstrument(Node):
    """Generic toolkit driver for a Zurich Instrument device.

    All device specific class are dervided from this class.
    It exposes the nodetree as also implements common functions valid for all
    devices.
    It also can be used directly, e.g. for instrument types that have not yet
    been specialized in toolkit.

    Args:
        serial (str): Serial number of the device, e.g. *'dev12000'*.
            The serial number can be found on the back panel of the instrument.
        device_type (str): Type of the device.
        session (ConnectionManager): Session to the Data Server
    """

    def __init__(self, serial: str, device_type:str, session,):
        self._serial = serial
        self._device_type = device_type
        self._session = session

        # HF2 does not support listNodesJSON so we have the information hardcoded
        # (the node of HF2 will not change any more so this is safe)
        preloaded_json = None
        if "HF2" in self._device_type:
            preloaded_json = self._load_preloaded_json(
                Path(__file__).parent / "nodedoc_hf2.json"
            )


        nodetree = NodeTree(
            self._session.daq_server,
            prefix_hide=self._serial,
            list_nodes=[f"/{self._serial}/*"],
            preloaded_json=preloaded_json,
        )
        # Add predefined parseres (in node_parser) to nodetree nodes
        nodetree.update_nodes(node_parser.get(self._device_type, {}))

        super().__init__(nodetree, tuple())

    def __repr__(self):
        return f"{self.__class__.__name__}({self._device_type},{self.serial})"

    def factory_reset(self, deep: bool = True) -> None:
        """Load the factory default settings.

        Arguments:
            deep (bool): A flag that specifies if a synchronisation
                should be performed between the device and the data
                server after loading the factory preset (default: True).
        """
        self.system.preset.load(1, deep=deep)
        logger.info(f"Factory preset is loaded to device {self.serial.upper()}.")

    def get_streamingnodes(self) -> dict:
        """Create a dictionary with all streaming nodes available"""
        streaming_nodes = {}
        for node, info in self:
            if "Stream" in info.get("Properties"):
                node_name = node.raw_tree[0][:-1] + node.raw_tree[1]
                if "pid" in node_name:
                    node_name += f"_{node.raw_tree[-1]}"
                streaming_nodes[node_name] = node
        return streaming_nodes

    def _load_preloaded_json(self, filename: Path):
        """Load a preloaded json and match the existing nodes.

        TODO
        """
        if not filename.is_file():
            return None
        raw_file = filename.open("r").read()

        raw_file = raw_file.replace("devxxxx", self.serial.lower())
        raw_file = raw_file.replace("DEVXXXX", self.serial.upper())
        json_raw = json.loads(raw_file)

        existing_nodes = self._session.daq_server.listNodes(
            f"/{self.serial}/*", recursive=True, leavesonly=True
        )

        preloaded_json = {}
        for node in existing_nodes:
            node_name = re.sub(r"(?<!values)\/[0-9]*?$", "/n", node.lower())
            node_name = re.sub(r"\/[0-9]*?\/", "/n/", node_name)
            json_element = copy.deepcopy(json_raw.get(node_name))
            if json_element:
                json_element["Node"] = node.upper()
                preloaded_json[node.lower()] = json_element
            elif not node.startswith("/zi/"):
                print(f"unkown node {node}")

        return preloaded_json

    @property
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
            >>> with device.set_transaction():
                    device.test[0].a(1)
                    device.test[1].a(2)
        """
        return self._root.set_transaction

    @property
    def serial(self) -> str:
        """instrument specify serial."""
        return self._serial

    @property
    def device_type(self) -> str:
        """Type of the instrument (e.g. MFLI)"""
        return self._device_type
