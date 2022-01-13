import logging
from collections.abc import MutableMapping
import numpy as np
import zhinst.deviceutils.shfqa as deviceutils
from zhinst.toolkit.nodetree import Node
from zhinst.toolkit.driver.base import BaseInstrument


logger = logging.getLogger(__name__)


class Waveforms(MutableMapping):
    def __init__(self):
        self._waveforms = {}

    def __getitem__(self, key: int):
        return self._waveforms[key]

    def __setitem__(self, key: int, value: np.array):
        self._waveforms[key] = self._get_raw_vector(value)

    def __delitem__(self, key: int):
        del self._waveforms[key]

    def __iter__(self):
        return iter(self._waveforms)

    def __len__(self):
        return len(self._waveforms)

    def _get_raw_vector(self, wave):
        """Return the raw vector for a slot that can be uploaded to the device

        Adjust the scaling of the waveform. The data is actually sent as complex
        values in the range of (-1, 1). The absolute value of each number is
        also limited to smaller or equal to one.

        Args:
            key (int): slot index
        """
        if len(wave) == 0:
            wave = np.zeros(1)
        max_value = np.max(np.abs(wave))
        wave = wave / max_value if max_value >= 1 else wave
        complex_data = wave.astype(complex)
        return complex_data


class Generator(Node):
    """Generator Module for a single `QAChannel`.

    The :class:`Generator` class implements basic functionality of
    the SHF Sequencer allowing the user to write and upload their
    *'.seqC'* code.
    In contrast to other AWG Sequencers, e.g. from the HDAWG, SHF
    Sequencer does not provide writing access to the Waveform Memories
    and hence does not come with predefined waveforms such as `gauss`
    or `ones`. Therefore, all waveforms need to be defined in Python
    and uploaded to the device using `upload_waveforms` method.

    Attributes:
    nodetree (:class: 'NodeTree'): nodetree of the device
    qa_index (int): index of the qa_channel the generator works on
    connection (:class: `ZIConnection`): Connection Object of the device.
    module (:class: 'AWGModuleConnection'): ziPython AWG module
    """

    def __init__(
        self,
        device: BaseInstrument,
        session,
        tree,
        index,
    ):
        super().__init__(device.root, tree)
        self._session = session
        self._device = device
        self._serial = device.serial
        self._index = index

    def wait_done(self, timeout: float = 10, sleep_time: float = 0.005) -> None:
        """Wait until the generator execution is finished.

        Arguments:
            timeout (float): The maximum waiting time in seconds for the
                generator (default: 10).
            sleep_time (float): Time in seconds to wait between
                requesting generator state

        Raises:
            RuntimeError: If continuous mode is enabled
            TimeoutError: If the sequencer program did not finish within the timout
        """
        if not self.single():
            raise RuntimeError(
                f"{repr(self)}: The generator is running in continuous mode, "
                "it will never be finished."
            )
        if not self.enable.wait_for_state_change(
            0, timeout=timeout, sleep_time=sleep_time
        ):
            raise TimeoutError(
                f"{repr(self)}: The exceution of the sequencer program did not finish "
                f"within the specified timeout ({timeout}s)."
            )

    def load_sequencer_program(self, sequencer_program, timeout: float = 10) -> None:
        """Compiles and loads a program to a specified sequencer.

        Args:
            sequencer_program (str): sequencer program to be uploaded
            timeout (float): maximum time to wait for the compilation on the
                device in seconds. (default = 10s)

        Raises:
            RuntimeError: If the upload or compilation failed.
        """
        deviceutils.load_sequencer_program(
            self._session.daq_server,
            self._serial,
            self._index,
            sequencer_program,
            self._session.awg_module,
            timeout=timeout,
        )

    def write_to_waveform_memory(
        self, waveforms: Waveforms, clear_existing: bool = True
    ) -> None:
        """Writes pulses to the waveform memory

        Args:
        """
        if self._device.num_qachannels == 4 and len(waveforms.keys()) > 0 and max(waveforms.keys()) >= 16:
            raise RuntimeError(
                "The SHFQA 4 channel has 16 waveform slots"
                f", but {max(waveforms.keys())} where specified"
            )
        elif self._device.num_qachannels == 2 and len(waveforms.keys()) > 0 and max(waveforms.keys()) >= 8:
            raise RuntimeError(
                "The SHFQA 2 channel has 8 waveform slots"
                f", but {max(waveforms.keys())} where specified"
            )
        deviceutils.write_to_waveform_memory(
            self._session.daq_server,
            self._serial,
            self._index,
            waveforms,
            clear_existing,
        )
