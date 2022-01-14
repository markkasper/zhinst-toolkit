import logging
import numpy as np
import zhinst.deviceutils.shfqa as deviceutils
from zhinst.toolkit.interface import AveragingMode
from zhinst.toolkit.nodetree import Node


logger = logging.getLogger(__name__)

class Readout(Node):
    """Readout Module"""

    def __init__(
        self,
        device,
        session,
        tree,
        index: int,
    ):
        super().__init__(device.root, tree)
        self._session = session
        self._device = device
        self._serial = device.serial
        self._index = index



    def configure_result_logger(
        self,
        result_source: str,
        result_length: int,
        num_averages: int = 1,
        averaging_mode: AveragingMode = AveragingMode.CYCLIC,
    ) -> None:
        """Configures the result logger for readout mode.

        Arguments:
        result_source (str): string-based tag to select the result source
                            in readout mode, e.g. "result_of_integration"
                            or "result_of_discrimination".

        result_length (int): number of results to be returned by the result logger

        num_averages (optional int): number of averages, will be rounded to 2^n

        averaging_mode (optional int): select the averaging order of the result, with 0 = cyclic
                                        and 1 = sequential.

        """
        deviceutils.configure_result_logger_for_readout(
            self._session.daq_server,
            self._serial,
            self._index,
            result_source,
            result_length,
            num_averages,
            int(averaging_mode),
        )

    def run(self) -> None:
        """Resets and enables the result logger"""
        deviceutils.enable_result_logger(
            self._session.daq_server,
            self._serial,
            self._index,
            "readout",
        )

    def stop(self, timeout: float = 10, sleep_time: float = 0.05) -> None:
        """Stop the result logger.

        Arguments:
            timeout (float): The maximum waiting time in seconds for the
                Readout (default: 10).
        Raises:
            TimeoutError: if the result logger could not been stoped within the
                given time.

        """
        self.result.enable(False)
        if not self.result.enable.wait_for_state_change(0):
            raise TimeoutError(
                f"{repr(self)}: The result logger could not been stoped "
                f"within the specified timeout ({timeout}s)."
            )

    def wait_done(self, timeout: float = 10, sleep_time: float = 0.05) -> None:
        """Wait until readout is finished.

        Arguments:
            timeout (float): The maximum waiting time in seconds for the
                Readout (default: 10).
            sleep_time (float): Time in seconds to wait between
                requesting Readout state

        Raises:
            TimeoutError: if the readout recording is not completed within the
                given time.

        """
        if not self.result.enable.wait_for_state_change(
            0, timeout=timeout, sleep_time=sleep_time
        ):
            raise TimeoutError(
                f"{repr(self)}: The readout did not finish "
                f"within the specified timeout ({timeout}s)."
            )

    def read(
        self,
        timeout: float = 10,
    ) -> np.array:
        """Waits until the logger finished recording and returns the measured data.

        Args:
            time_out (float): maximum time to wait for data in seconds (default = 10s)

        Returns:
            result (array): array containing the result logger data

        """
        return deviceutils.get_result_logger_data(
            self._session.daq_server,
            self._serial,
            self._index,
            "readout",
            timeout
        )

    def set_integration_weight(self, index:int, waveform:np.array) -> None:
        """Set the complex-valued waveform for one intergration weight.

        The valid range of the waveform values is between -1.0 and +1.0
        for both the real and imaginary part.

        Args:
            index (int): weight index
            waveform (np.array) waveform
        """
        self.integration.weights[index].wave(np.zeros(4096, dtype=np.complex))
        if self.integration.length() != len(waveform):
            logger.warning(
                f"The integration length is set to {self.integration.length()} "
                f"but it does not match the length of the weights "
                f"vector. It will be automatically set to "
                f"{len(waveform)}."
            )
            self.integration.length(len(waveform))
        self.integration.weights[index].wave(waveform)
