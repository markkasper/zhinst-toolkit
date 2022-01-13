# Copyright (C) 2021 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

import logging
from zhinst.toolkit.nodetree import Node
from zhinst.toolkit.driver.parsers import Parse
from zhinst.toolkit import AveragingMode, MappingMode, TriggerImpedance
from zhinst.utils.shf_sweeper import (
    ShfSweeper as CoreSweeper,
    RfConfig,
    TriggerConfig,
    SweepConfig,
    AvgConfig,
)
from zhinst.toolkit.helper import lazy_property

logger = logging.getLogger(__name__)


class SHFSweeper:
    """SHFweeper Module"""

    def __init__(
        self,
        device,
        session,
        index: int,
    ):
        self._session = session
        self._device = device
        self._serial = device.serial
        self._index = index
        self._module = CoreSweeper(session.daq_server, self._serial)
        self._nodetree = device.root
        self._trigger_level = 0.5
        self._trigger_impedance = TriggerImpedance.OHM50
        self._start_freq = -300e6
        self._stop_freq = 300e6
        self._num_points = 100
        self._mapping = MappingMode.LIN
        self._num_averages = 1
        self._averaging_mode = AveragingMode.CYCLIC

    def __repr__(self):
        return f"Sweeper Module for QAChannel {self._index}"

    def run(self):
        """Perform a sweep with the specified settings.

        This method eventually wraps around the `run` method of
        `zhinst.utils.shf_sweeper`
        """
        self._update_qachannel_params()
        self._update_trigger_settings()
        self._update_sweep_params()
        self._update_averaging_settings()
        self._module.run()

    def get_result(self):
        """Get the measurement data of the last sweep.

        This method eventually wraps around the `get_result` method of
        `zhinst.utils.shf_sweeper`

        Returns:
             A dictionary with measurement data of the last sweep

        """
        return self._module.get_result()

    def plot(self):
        """Plot power over frequency for last sweep.

        This method eventually wraps around the `plot` method of
        `zhinst.utils.shf_sweeper`
        """
        return self._module.plot()

    def _update_qachannel_params(self):
        qachannel_params = RfConfig(
            channel=self._index,
            input_range=int(self._nodetree.qachannels[self._index].input.range()),
            output_range=int(self._nodetree.qachannels[self._index].output.range()),
            center_freq=self._nodetree.qachannels[self._index].centerfreq(),
        )
        self._module.configure(rf_config=qachannel_params)

    def _update_trigger_settings(self):
        trig_config = TriggerConfig(
            source=self.trigger_source(),
            level=self._trigger_level,
            imp50=self._trigger_impedance.value,
        )
        self._module.configure(trig_config=trig_config)

    def _update_sweep_params(self):
        sweep_params = SweepConfig(
            start_freq=self._start_freq,
            stop_freq=self._stop_freq,
            num_points=self._num_points,
            mapping=self._mapping.value,
            oscillator_gain=self.oscillator_gain(),
        )
        self._module.configure(sweep_config=sweep_params)

    def _update_averaging_settings(self):
        avg_config = AvgConfig(
            integration_time=self.integration_time(),
            num_averages=self._num_averages,
            mode="cyclic" if self._averaging_mode == 0 else "sequential",
        )
        self._module.configure(avg_config=avg_config)

    @lazy_property
    def oscillator_gain(self) -> Node:
        return self._nodetree.qachannels[self._index].oscs[0].gain

    @lazy_property
    def oscillator_freq(self) -> Node:
        return self._nodetree.qachannels[self._index].oscs[0].freq

    @lazy_property
    def integration_time(self) -> Node:
        node = Node(
            self._nodetree, ["qachannels", str(self._index), "spectroscopy", "time"]
        )
        self._nodetree.update_node(
            node,
            {
                "Node": self.integration_length.node,
                "Description": "Sets the integration length in Spectroscopy mode in unit "
                "of seconds. Up to 16.7 ms can be recorded, which "
                "corresponds to 33.5 MSa (2^25 samples).",
                "Type": "Double",
                "Properties": "Read, Write, Setting",
                "Unit": "s",
                "GetParser": Parse.shfqa_samples2time,
                "SetParser": Parse.shfqa_time2samples,
            },
            add=True,
        )
        return node

    @lazy_property
    def integration_length(self) -> Node:
        return self._nodetree.qachannels[self._index].spectroscopy.length

    @lazy_property
    def integration_delay(self) -> Node:
        return self._nodetree.qachannels[self._index].spectroscopy.delay

    @lazy_property
    def trigger_source(self) -> Node:
        return self._nodetree.qachannels[self._index].spectroscopy.trigger.channel

    @property
    def trigger_level(self) -> float:
        """trigger level for the sweeper"""
        return self._trigger_level

    @trigger_level.setter
    def trigger_level(self, level: float) -> None:
        self._trigger_level = level
        self._update_trigger_settings()

    @property
    def trigger_impedance(self) -> TriggerImpedance:
        """trigger input impedance setting for the sweeper"""
        return self._trigger_impedance

    @trigger_impedance.setter
    def trigger_impedance(self, imp: TriggerImpedance) -> None:
        self._trigger_impedance = imp
        self._update_trigger_settings()

    @property
    def start_frequency(self) -> float:
        """Start frequency in Hz of the sweeper"""
        return self._start_freq

    @start_frequency.setter
    def start_frequency(self, freq: float) -> None:
        self._start_freq = freq
        self._update_sweep_params()

    @property
    def stop_frequency(self) -> float:
        """Stop frequency in Hz of the sweeper"""
        return self._stop_freq

    @stop_frequency.setter
    def stop_frequency(self, freq: float) -> None:
        self._stop_freq = freq
        self._update_sweep_params()

    @property
    def output_freq(self) -> float:
        """Output frequency

        The carrier frequency in Hz of the microwave signal at the
        Out connector. This frequency corresponds to the sum of the
        Center Frequency and the Offset Frequency.
        """
        return (
            self._nodetree.qachannels[self._index].centerfreq() + self.oscillator_freq()
        )

    @property
    def num_points(self) -> int:
        """Number of frequency points for the sweeper."""
        return self._num_points

    @num_points.setter
    def num_points(self, num_points: int) -> None:
        self._num_points = num_points
        self._update_sweep_params()

    @property
    def mapping(self) -> MappingMode:
        """Number of averages for the sweeper.

        Number of averages specifies how many times a frequency point
        will be measured and averaged."""
        return self._mapping

    @mapping.setter
    def mapping(self, mapping: MappingMode) -> None:
        self._mapping = mapping
        self._update_sweep_params()

    @property
    def num_averages(self) -> int:
        """Number of averages for the sweeper.

        Number of averages specifies how many times a frequency point
        will be measured and averaged."""
        return self._num_averages

    @num_averages.setter
    def num_averages(self, num: int) -> None:
        self._num_averages = num
        self._update_averaging_settings()

    @property
    def averaging_mode(self) -> AveragingMode:
        """Averaging mode for the sweeper"""
        return self._averaging_mode

    @averaging_mode.setter
    def averaging_mode(self, mode: AveragingMode) -> None:
        self._averaging_mode = mode
        self._update_averaging_settings()
