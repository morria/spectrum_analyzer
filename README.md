# CLI Spectrum Analyzer

This is a simple command line interface (CLI) spectrum analyzer meant to display the output of [hackrf_sweep](https://hackrf.readthedocs.io/en/latest/hackrf_tools.html#hackrf-sweep).


```shell
hackrf_sweep -a 1 -p1 -f 90:102 -w 50000 | ./spectrum_analyzer.py
```

which will produce a spectroscope output such as follows.

![alt text](demo.png)

