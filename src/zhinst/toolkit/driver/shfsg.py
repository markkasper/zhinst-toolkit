# Copyright (C) 2021 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

""" Zurich Instruments Toolkit (zhinst-toolkit) SHFSG Instrument Driver.

This driver provides a high-level controller for the SHFSG Zurich Instrument
devices for Zurich Instruments Toolkit (zhinst-toolkit). It is based on
the LabOne Python API ziPython and forms the basis for instrument drivers used
in QCoDeS and Labber.
"""

import logging
import warnings
from typing import List
from zhinst.toolkit.nodetree import Node
from zhinst.toolkit.helper import lazy_property
from zhinst.toolkit.driver.base import BaseInstrument
from zhinst.toolkit.driver.modules.awg import AWGModule


logger = logging.getLogger(__name__)


class SGChannel(Node):
    """Signal Generator Channel for the SHFSG.

    :class:`SGChannel` implements basic functionality to configure SGChannel
    settings of the :class:`SHFSG` instrument.

    Attributes:
    nodetree (:class: `NodeTree`): Nodetree for the current SHFSG device.
    index (int): Index of the QAChannel
    connection (:class: `ZIConnection`): Connection Object of the device.
    serial (str): Serial number of the device.
    """

    def __init__(
        self,
        device: "SHFSG",
        session,
        tree,
    ):
        super().__init__(device.root, tree)
        self._index = int(tree[-1])
        self._device = device
        self._serial = device.serial
        self._session = session

    @lazy_property
    def awg(self) -> AWGModule:
        """Generator module for this QAChannel"""
        return AWGModule(
            self._device,
            self._session,
            self._tree + ("awg",),
            self._index,
            ct_schema_url="https://docs.zhinst.com/shfsg/commandtable/v1_0/schema",
        )


class SHFSG(BaseInstrument):
    """High-level driver for the Zurich Instruments SHFSG Signal Generator.

    Inherits from :class:`BaseInstrument` and defines device specific
    methods and properties.

    Args:
        serial (str): Serial number of the device, e.g. *'dev12000'*.
            The serial number can be found on the back panel of the instrument.
        device_type (str): Type of the device.
        session (ConnectionManager): Session to the Data Server
    """

    def __init__(self, serial: str, device_type: str, session):
        BaseInstrument.__init__(self, serial, device_type, session)

    def factory_reset(self, deep: bool = True) -> None:
        """Load the factory default settings.

        Arguments:
            sync (bool): A flag that specifies if a synchronisation
                should be performed between the device and the data
                server after loading the factory preset (default: True).
        """
        warnings.warn("Factory preset is not yet supported for SHFSG.", RuntimeWarning)
        logger.warning("Factory preset is not yet supported in SHFSG.")

    def enable_qccs_mode(self) -> None:
        """Configure the instrument to work with PQSC

        This method sets the reference clock source to
        connect the instrument to the PQSC.
        """
        self.system.clocks.referenceclock.in_.source(2)

    def enable_manual_mode(self) -> None:
        """Configure the instrument to work without external triggers/devices

        This method sets the reference clock source to internal.
        """
        self.system.clocks.referenceclock.in_.source(0)

    @property
    def num_sgchannels(self) -> int:
        """Number of Signal Generator Channels"""
        # TODO get from device_type
        return len(self._root.get_node_info("sgchannels/*/centerfreq"))

    @lazy_property
    def sgchannels(self) -> List[SGChannel]:
        """SGChannels"""
        return [
            SGChannel(self, self._session, self._tree + ("sgchannels", str(i)))
            for i in range(self.num_sgchannels)
        ]
