# Copyright (C) 2020 Zurich Instruments
#
# This software may be modified and distributed under the terms
# of the MIT license. See the LICENSE file for details.

import numpy as np

from zhinst.toolkit.control.drivers.base import BaseInstrument, AWGCore, ZHTKException
from zhinst.toolkit.control.nodetree import Parameter
from zhinst.toolkit.control.parsers import Parse
from zhinst.toolkit.interface import DeviceTypes


MAPPINGS = {
    "result_source": {
        0: "Crosstalk",
        1: "Threshold",
        2: "Rotation",
        4: "Crosstalk Correlation",
        5: "Threshold Correlation",
        7: "Integration",
    }
}


class UHFQA(BaseInstrument):
    """
    High-level controller for UHFQA. Inherits from BaseInstrument and defines 
    UHFQA specific methods. The property awg_connection accesses the 
    connection's awg module and is used in the AWG core as 
    awg._parent._awg_module

    The UHFQA has one awg core and ten ReadoutChannels that can  be accessed as 
    properties of the object.

    """

    def __init__(self, name, serial, **kwargs):
        super().__init__(name, DeviceTypes.UHFQA, serial, **kwargs)
        self._awg = AWG(self, 0)
        self._channels = [ReadoutChannel(self, i) for i in range(10)]
        self.integration_time = Parameter(
            self,
            dict(
                Node="qas/0/integration/length",
                Description="The integration time of the QA Integration unit.",
                Type="Double",
                Properties="Read, Write",
                Unit="s",
            ),
            device=self,
            set_parser=Parse.uhfqa_time2samples,
            get_parser=Parse.uhfqa_samples2time,
        )
        self.result_source = Parameter(
            self,
            dict(
                Node="qas/0/result/source",
                Description="The signal source for the QA Results unit. One of {'Crosstalk', 'Threshold', 'Rotation', 'Crosstalk Correlation', 'Threshold Correlation', 'Integration'}.",
                Type="Integer",
                Properties="Read, Write",
                Unit="None",
            ),
            device=self,
            mapping=MAPPINGS["result_source"],
        )

    def connect_device(self, nodetree=True):
        super().connect_device(nodetree=nodetree)
        self.awg._setup()

    def crosstalk_matrix(self, matrix=None):
        if matrix is None:
            m = np.zeros((10, 10))
            for r in range(10):
                for c in range(10):
                    m[r, c] = self._get(f"qas/0/crosstalk/rows/{r}/cols/{c}")
            return m
        else:
            rows, cols = matrix.shape
            if rows > 10 or cols > 10:
                raise ValueError(
                    f"The shape of the given matrix is {rows} x {cols}. The maximum size is 10 x 10."
                )
            for r in range(rows):
                for c in range(cols):
                    self._set(f"qas/0/crosstalk/rows/{r}/cols/{c}", matrix[r, c])

    def enable_readout_channels(self, channels=range(10)):
        for i in channels:
            if i not in range(10):
                raise ValueError(f"The channel index {i} is out of range!")
            self.channels[i].enable()

    def disable_readout_channels(self, channels=range(10)):
        for i in channels:
            if i not in range(10):
                raise ValueError(f"The channel index {i} is out of range!")
            self.channels[i].disable()

    def arm(self, length=None, averages=None):
        """Prepare UHFQA for result acquisition.

        This method enables the QA Results Acquisition and resets the acquired 
        points. Optionally, the *result length* and *result averages* can be set 
        when specified as keyword arguments. If they are not specified, they are 
        not changed.  

        Keyword Arguments:
            length (int): If specified, the length of the result vector will be 
                set before arming the UHFQA readout. (default: None)
            averages (int): If specified, the result averages will be set before 
                arming the UHFQA readout. (default: None)

        """
        if length is not None:
            self._set("qas/0/result/length", int(length))
        if averages is not None:
            self._set("qas/0/result/averages", int(averages))
        self._set("qas/0/result/enable", 1)
        # toggle node value from 0 to 1 for reset
        self._set("qas/0/result/reset", 0)
        self._set("qas/0/result/reset", 1)

    def _init_settings(self):
        settings = [
            ("awgs/0/single", 1),
        ]
        self._set(settings)

    @property
    def awg(self):
        return self._awg

    @property
    def channels(self):
        return self._channels

    @property
    def _awg_connection(self):
        self._check_connected()
        return self._controller._connection.awg_module


class AWG(AWGCore):
    """
    Device-specific AWG for UHFQA with properties like ouput or gains and 
    sequence specific settings for the UHFQA. Inherits from AWGCore.

    """

    def __init__(self, parent, index):
        super().__init__(parent, index)
        self.output1 = Parameter(
            self,
            dict(
                Node="sigouts/0/on",
                Description="Enables or disables both ouputs of the AWG. Either can be {'1', '0'} or {'on', 'off'}.",
                Type="Integer",
                Properties="Read, Write",
                Unit="None",
            ),
            device=self._parent,
            set_parser=Parse.set_on_off,
            get_parser=Parse.get_on_off,
        )
        self.output2 = Parameter(
            self,
            dict(
                Node="sigouts/1/on",
                Description="Enables or disables both ouputs of the AWG. Either can be {'1', '0'} or {'on', 'off'}.",
                Type="Integer",
                Properties="Read, Write",
                Unit="None",
            ),
            device=self._parent,
            set_parser=Parse.set_on_off,
            get_parser=Parse.get_on_off,
        )
        self.gain1 = Parameter(
            self,
            dict(
                Node="awgs/0/outputs/0/amplitude",
                Description="Sets the gain of the first output channel.",
                Type="Double",
                Properties="Read, Write",
                Unit="None",
            ),
            device=self._parent,
            set_parser=Parse.amp1,
        )
        self.gain2 = Parameter(
            self,
            dict(
                Node="awgs/0/outputs/1/amplitude",
                Description="Sets the gain of the second output channel.",
                Type="Double",
                Properties="Read, Write",
                Unit="None",
            ),
            device=self._parent,
            set_parser=Parse.amp1,
        )

    def _apply_sequence_settings(self, **kwargs):
        if "sequence_type" in kwargs.keys():
            t = kwargs["sequence_type"]
            allowed_sequences = [
                "Simple",
                "Readout",
                "CW Spectroscopy",
                "Pulsed Spectroscopy",
                "Custom",
            ]
            if t not in allowed_sequences:
                raise ZHTKException(
                    f"Sequence type {t} must be one of {allowed_sequences}!"
                )
            # apply settings depending on sequence type
            elif t == "CW Spectroscopy":
                self._apply_cw_settings()
            elif t == "Pulsed Spectroscopy":
                self._apply_pulsed_settings()
            elif t == "Readout":
                self._apply_readout_settings()
            else:
                self._apply_base_settings()
        # apply settings dependent on trigger type
        if "trigger_mode" in kwargs.keys():
            if kwargs["trigger_mode"] == "External Trigger":
                self._apply_trigger_settings()

    def _apply_base_settings(self):
        settings = [
            ("sigouts/*/enables/*", 0),
            ("sigouts/*/amplitudes/*", 0),
            ("awgs/0/outputs/*/mode", 0),
            ("qas/0/integration/mode", 0),
        ]
        self._parent._set(settings)

    def _apply_cw_settings(self):
        settings = [
            ("sigouts/0/enables/0", 1),
            ("sigouts/1/enables/1", 1),
            ("sigouts/0/amplitudes/0", 1),
            ("sigouts/1/amplitudes/1", 1),
            ("awgs/0/outputs/*/mode", 0),
            ("qas/0/integration/mode", 1),
        ]
        self._parent._set(settings)
        self._parent.disable_readout_channels(range(10))

    def _apply_pulsed_settings(self):
        settings = [
            ("sigouts/*/enables/*", 0),
            ("sigouts/*/amplitudes/*", 0),
            ("awgs/0/outputs/*/mode", 1),
            ("qas/0/integration/mode", 1),
        ]
        self._parent._set(settings)
        self._parent.disable_readout_channels(range(10))

    def _apply_readout_settings(self):
        settings = [
            ("sigouts/*/enables/*", 0),
            ("awgs/0/outputs/*/mode", 0),
            ("qas/0/integration/mode", 0),
        ]
        self._parent._set(settings)

    def _apply_trigger_settings(self):
        settings = [
            ("/awgs/0/auxtriggers/*/channel", 0),
            ("/awgs/0/auxtriggers/*/slope", 1),
        ]
        self._parent._set(settings)

    def outputs(self, value=None):
        if value is None:
            return self.output1(), self.output2()
        else:
            if isinstance(value, tuple) or isinstance(value, list):
                if len(value) != 2:
                    raise ZHTKException(
                        "The values should be specified as a tuple, e.g. ('on', 'off')."
                    )
                return self.output1(value[0]), self.output2(value[1])
            else:
                raise ZHTKException("The value must be a tuple or list of length 2!")

    def update_readout_params(self):
        if self.sequence_params["sequence_type"] == "Readout":
            freqs = []
            amps = []
            phases = []
            for ch in self._parent.channels:
                if ch.enabled():
                    freqs.append(ch.readout_frequency())
                    amps.append(ch.readout_amplitude())
                    phases.append(ch.phase_shift())
            self.set_sequence_params(
                readout_frequencies=freqs, readout_amplitudes=amps, phase_shifts=phases,
            )
        else:
            raise ZHTKException("AWG Sequence type needs to be 'Readout'")

    def compile(self):
        if self.sequence_params["sequence_type"] == "Readout":
            self.update_readout_params()
        super().compile()


"""
Implements a Readout Channel for UHFQA. 

Parameters:
    rotation
    threshold
    result
    index
    enabled
    readout_frequency
    readout_amplitude
    phase_shift

"""


class ReadoutChannel:
    def __init__(self, parent, index):
        if index not in range(10):
            raise ValueError(f"The channel index {index} is out of range!")
        self._index = index
        self._parent = parent
        self._enabled = False
        self._readout_frequency = 100e6
        self._readout_amplitude = 1
        self._phase_shift = 0
        self.rotation = Parameter(
            self,
            dict(
                Node=f"qas/0/rotations/{self._index}",
                Description="Sets the rotation of the readout channel in degrees.",
                Type="Double",
                Properties="Read, Write",
                Unit="Degrees",
            ),
            device=self._parent,
            set_parser=Parse.deg2complex,
            get_parser=Parse.complex2deg,
        )
        self.threshold = Parameter(
            self,
            dict(
                Node=f"qas/0/thresholds/{self._index}/level",
                Description="Sets the threshold of the readout channel.",
                Type="Double",
                Properties="Read, Write",
                Unit="None",
            ),
            device=self._parent,
        )
        self.result = Parameter(
            self,
            dict(
                Node=f"qas/0/result/data/{self._index}/wave",
                Description="Returns the result vector of the readout channel.",
                Type="Numpy array",
                Properties="Read",
                Unit="None",
            ),
            device=self._parent,
            get_parser=self._average_result,
        )

    @property
    def index(self):
        return self._index

    def enabled(self):
        return self._enabled

    def enable(self):
        self._enabled = True
        self._parent._set("qas/0/integration/mode", 0)
        self._parent.integration_time(2e-6)
        self._set_int_weights()

    def disable(self):
        self._enabled = False
        self._reset_int_weights()

    def readout_frequency(self, freq=None):
        if freq is None:
            return self._readout_frequency
        else:
            Parse.greater0(freq)
            self._readout_frequency = freq
            self._set_int_weights()
            return self._readout_frequency

    def readout_amplitude(self, amp=None):
        if amp is None:
            return self._readout_amplitude
        else:
            Parse.amp1(amp)
            self._readout_amplitude = amp
            return self._readout_amplitude

    def phase_shift(self, ph=None):
        if ph is None:
            return self._phase_shift
        else:
            self._phase_shift = Parse.phase(ph)
            return self._phase_shift

    def _reset_int_weights(self):
        node = f"/qas/0/integration/weights/"
        self._parent._set(node + f"{self._index}/real", np.zeros(4096))
        self._parent._set(node + f"{self._index}/imag", np.zeros(4096))

    def _set_int_weights(self):
        self._reset_int_weights()
        l = self._parent._get("qas/0/integration/length")
        freq = self.readout_frequency()
        node = f"/qas/0/integration/weights/{self._index}/"
        self._parent._set(node + "real", self._demod_weights(l, freq, 0))
        self._parent._set(node + "imag", self._demod_weights(l, freq, 90))

    def _demod_weights(self, length, freq, phase):
        if length > 4096:
            raise ValueError(
                "The maximum length of the integration weights is 4096 samples."
            )
        if freq <= 0:
            raise ValueError("This frequency must be positive.")
        clk_rate = 1.8e9
        x = np.arange(0, length)
        y = np.sin(2 * np.pi * freq * x / clk_rate + np.deg2rad(phase))
        return y

    def _average_result(self, result):
        n_averages = self._parent._get("qas/0/result/averages")
        return result / n_averages

    def __repr__(self):
        s = f"Readout Channel {self._index}:  {super().__repr__()}\n"
        s += f"     rotation          : {self.rotation()}\n"
        s += f"     threshold         : {self.threshold()}\n"
        if self._enabled:
            s += f"     readout_frequency : {self.readout_frequency()}\n"
            s += f"     readout_amplitude : {self.readout_amplitude()}\n"
            s += f"     phase_shift       : {self.phase_shift()}\n"
        else:
            s += "      Weighted Integration Disabled\n"
        return s
