#include "main.h"

// a sample exported function

/*
This is a mini library to copy the buffer memory from a pointer to a new pointer.
*/
#include "string.h"
void DLL_EXPORT memCopier (void* destination, void *  source, size_t const size)
{
    /* It is important that you keep the factor in front of 'size' as 2.
    This is because the card reads every sample to have a size of 2 bytes.
    This is what we are mimicing here. */
memcpy(destination,source,2*size);


/*
int i;
for(i=0;i<size;i++)
{
int var = *(((int*) (source))+i);
char var2[10];
itoa(var,var2,10);

MessageBoxA(0, var2, "DLL Message", MB_OK | MB_ICONINFORMATION);
}

*/
}

void DLL_EXPORT memMover (void* destination, void *  source, size_t const size)
{

memmove(destination,source,2*size);

}

void DLL_EXPORT memCopier2 (void* destination, void *  source, size_t const size)
{

size_t i;
for (i=0;i<2*size;i++)
{
    ((short*)destination)[i] =  ((short*)source)[i];
}


}



void DLL_EXPORT SomeFunction(const LPCSTR sometext)
{
    MessageBoxA(0, sometext, "DLL Message", MB_OK | MB_ICONINFORMATION);
}

extern "C" DLL_EXPORT BOOL APIENTRY DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved)
{
    switch (fdwReason)
    {
        case DLL_PROCESS_ATTACH:
            // attach to process
            // return FALSE to fail DLL load
            break;

        case DLL_PROCESS_DETACH:
            // detach from process
            break;

        case DLL_THREAD_ATTACH:
            // attach to thread
            break;

        case DLL_THREAD_DETACH:
            // detach from thread
            break;
    }
    return TRUE; // succesful
}
