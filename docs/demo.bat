for /l %%n in (0,1,49) do (
	echo %%n
	echo %%n > "C:\Users\qgtx64\DocumentsCDrive\QSUM\Training\currentfile.txt"
	copy "C:\Users\qgtx64\DocumentsCDrive\QSUM\Training\TestSingleAtomIms\TestIm%%n.asc" "C:\Users\qgtx64\DocumentsCDrive\QSUM\Training\test\CameraIm\CameraIm.asc"
	ping 127.0.0.1 -n 1 -w 500> nul
	timeout /t 1
)