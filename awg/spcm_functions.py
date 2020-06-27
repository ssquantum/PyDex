def adjuster (requested_freq,samplerate,memSamples):
    """
    This function corrects the requested frequency to account for the fractional number of 
    cycles the card can produce for a given memory sample.
    The function takes the value of the requested frequency in MHz.
    The values of samplerate and memSamples are directly taken from the setup code to avoid small errors.
    These are typically given in Hz and bytes respectively.
    """
    nCycles = round(requested_freq/samplerate*memSamples*10**6)
    newFreq = round(nCycles*samplerate/memSamples/10**6,6)
    return newFreq



def bytes_to_int(bytes):
    """
    Ok, now I understand that although the spirit of this is correct,
    the execution of this function is wrong. Technically what I was trying to do
    is to cast a void type into an int, but here I did not take into account the difference
    in BITS between the two.
    """
    result=0
    for b in bytes:
        result = result*256 +int(b)
    return result


def int_to_bytes(value,length):
    result = []
    for i in range(0,length):
        result.append(value >> (i*8) & 0xff)
    result.reverse()
    return result
    
def save(vbuffer, pbuffer,val):
    """
    Just a simple function for collecting and saving the pn and pv Buffer elements.
    This exploits the simple function byte_to_int to convert the data from buffer type to int.
    vbuffer should simply be pvBuffer
    pbuffer should simple be pnBuffer
    val here must be a string.
    Feel free to change the path or modify.
    """
    vBuffer = np.zeros(llMemSamples.value)
    pBuffer = np.zeros(llMemSamples.value)
    for i in range(0,llMemSamples.value):
        vBuffer[i] = bytes_to_int(vbuffer[i])
    for i in range(0,llMemSamples.value):
        pBuffer[i] = pbuffer[i]
    numpy.savetxt("./sampling_test/"+val+"_pvBuffer.csv",vBuffer)
    numpy.savetxt("./sampling_test/"+val+"_pnBuffer.csv",pBuffer)