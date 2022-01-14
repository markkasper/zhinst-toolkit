# Copyright (C) 2021 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

""" Zurich Instruments Toolkit (zhinst-toolkit) SHFQA Instrument Driver.

This driver provides a high-level controller for the SHFQA Zurich Instrument
devices for Zurich Instruments Toolkit (zhinst-toolkit). It is based on
the LabOne Python API ziPython and forms the basis for instrument drivers used
in QCoDeS and Labber.
"""

import logging
import warnings
from typing import List
import zhinst.deviceutils.shfqa as deviceutils
from zhinst.toolkit.interface import SHFQAChannelMode
from zhinst.toolkit.nodetree import Node
from zhinst.toolkit.helper import lazy_property, NodeList
from zhinst.toolkit.driver.base import BaseInstrument
from zhinst.toolkit.driver.modules.generator import Generator
from zhinst.toolkit.driver.modules.readout import Readout
from zhinst.toolkit.driver.modules.shfqa_sweeper import SHFSweeper
from zhinst.toolkit.driver.modules.shfqa_scope import SHFScope


logger = logging.getLogger(__name__)


class QAChannel(Node):
    """Quantum Analyser Channel for the SHFQA.

    :class:`QAChannel` implements basic functionality to configure QAChannel
    settings of the :class:`SHFQA` instrument.
    Besides the :class:`Generator`, :class:`Readout` and :class:`Sweeper`
    moduels it also gives easy access to commonly used `QAChannel` parameters.

    Attributes:
    nodetree (:class: `NodeTree`): Nodetree for the current SHFQA device.
    index (int): Index of the QAChannel
    connection (:class: `ZIConnection`): Connection Object of the device.
    serial (str): Serial number of the device.
    """

    def __init__(
        self,
        device: "SHFQA",
        session,
        tree,
    ):
        super().__init__(device.root, tree)
        self._index = int(tree[-1])
        self._device = device
        self._serial = device.serial
        self._session = session

    def configure_channel(
        self,
        input_range: int,
        output_range: int,
        center_frequency: float,
        mode: SHFQAChannelMode,
    ) -> None:
        """Configures the RF input and output of a specified channel.

        Args:
            input_range (int): maximal range of the signal input power in dbM
            output_range (int): maximal range of the signal output power in dbM
            center_frequency (float): center Frequency of the analysis band
            mode (SHFQAChannelMode): select between spectroscopy and readout mode.
        """
        deviceutils.configure_channel(
            self._session.daq_server,
            self._serial,
            self._index,
            input_range,
            output_range,
            center_frequency,
            mode.value,
        )

    @lazy_property
    def num_integrations(self) -> int:
        """Number of integration units per qachannel"""
        return len(self._root.get_node_info(self.readout.discriminators["*"].threshold))

    @lazy_property
    def generator(self) -> Generator:
        """Generator module for this QAChannel"""
        return Generator(
            self._device, self._session, self._tree + ("generator",), self._index
        )

    @lazy_property
    def readout(self) -> Readout:
        """Readout module for this QAChannel"""
        return Readout(
            self._device, self._session, self._tree + ("readout",), self._index
        )

    @lazy_property
    def sweeper(self) -> SHFSweeper:
        """Sweeper module for this QAChannel"""
        return SHFSweeper(self._device, self._session, self._index)


class SHFQA(BaseInstrument):
    """High-level driver for the Zurich Instruments SHFQA Quantum Analyzer.

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
        warnings.warn("Factory preset is not yet supported for SHFQA.", RuntimeWarning)
        logger.warning("Factory preset is not yet supported in SHFQA.")

    def start_continuous_sw_trigger(self, num_triggers: int, wait_time: float) -> None:
        """Issues a specified number of software triggers with a certain wait time
        in between. The function guarantees reception and proper processing of
        all triggers by the device, but the time between triggers is
        non-deterministic by nature of software triggering. Only use this
        function for prototyping and/or cases without strong timing requirements.

        Args:
            num_triggers (int): number of triggers to be issued
            wait_time (float): time between triggers in seconds
        """

        deviceutils.start_continuous_sw_trigger(
            self._session.daq_server, self.serial, num_triggers, wait_time
        )

    @lazy_property
    def num_qachannels(self) -> int:
        """Number of Quantum Analyser Channels"""
        return len(self._root.get_node_info("qachannels/*/input/on"))

    @property
    def num_scopes(self) -> int:
        """Number of Scopes."""
        return 1

    @lazy_property
    def max_qubits_per_channel(self) -> int:
        """Returns the maximum number of supported qubits per channel."""
        return deviceutils.max_qubits_per_channel(
            self.connection.daq_server, self.serial
        )

    @lazy_property
    def qachannels(self) -> List[QAChannel]:
        """QAChannels"""
        return NodeList(
            [
                QAChannel(self, self._session, self._tree + ("qachannels", str(i)))
                for i in range(self.num_qachannels)
            ],
            self._root,
            self._tree + ("qachannels",),
        )

    @lazy_property
    def scopes(self) -> List[SHFScope]:
        """Scopes"""
        return NodeList([
            SHFScope(self, self._session, self._tree + ("scopes", str(i)))
            for i in range(self.num_scopes)
        ],
            self._root,
            self._tree + ("qachannels",),
        )
