import numpy as np


class Waveform(object):
    def __init__(self, wave1, wave2, granularity=16, align_start=True):
        self.__granularity = granularity
        self.__align_start = align_start
        self.__buffer_length = self.__round_up(max(len(wave1), len(wave2), 32))
        self.__data = self.__interleave_waveforms(wave1, wave2)

    @property
    def data(self):
        return self.__data

    @property
    def buffer_length(self):
        return self.__buffer_length

    def __interleave_waveforms(self, x1, x2):
        if len(x1) == 0:
            x1 = np.zeros(1)
        if len(x2) == 0:
            x2 = np.zeros(1)

        n = max(len(x1), len(x2))
        n = min(n, self.buffer_length)
        m1, m2 = np.max(np.abs(x1)), np.max(np.abs(x2))
        data = np.zeros((2, self.buffer_length))

        if self.__align_start:
            if len(x1) > n:
                data[0, :n] = x1[:n] / m1 if m1 >= 1 else x1[:n]
            else:
                data[0, : len(x1)] = x1 / m1 if m1 >= 1 else x1
            if len(x2) > n:
                data[1, :n] = x2[:n] / m2 if m2 >= 1 else x2[:n]
            else:
                data[1, : len(x2)] = x2 / m2 if m2 >= 1 else x2
        else:
            if len(x1) > n:
                data[0, :n] = x1[len(x1) - n :] / m1 if m1 >= 1 else x1[len(x1) - n :]
            else:
                data[0, (self.buffer_length - len(x1)) :] = x1 / m1 if m1 >= 1 else x1

            if len(x2) > n:
                data[1, :n] = x2[len(x2) - n :] / m2 if m2 >= 1 else x2[len(x2) - n :]
            else:
                data[1, (self.buffer_length - len(x2)) :] = x2 / m2 if m2 >= 1 else x2

        interleaved_data = (data.reshape((-2,), order="F") * (2 ** 15 - 1)).astype(
            "int16"
        )
        return interleaved_data

    def __round_up(self, n):
        m, rest = divmod(n, self.__granularity)
        if not rest:
            return n
        else:
            return (m + 1) * self.__granularity