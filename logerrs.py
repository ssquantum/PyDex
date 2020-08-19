"""
Martin Lichtman
created = 2013-10-07
modified >= 2013-10-07
cs_errors.py (see https://github.com/QuantumQuadrate/CsPyController/)
Exceptions for use in experimental controll software.
"""
__author__ = 'Martin Lichtman'

import logging
import logging.handlers

import colorlog

class PauseError(Exception):
    """This class is defined so we can raise an exception to have the experiment pause immediately.
    Usually this will be raised in the except clause after another error is caught.
    We want to be able to have try-except blocks for tricky parts of the code, but then still have the experiment pause
    as soon as possible.  We could just raise an Exception at this point, but this allows us to keep better track of what has
    happened, and to not log a second error.
    The preferred usage is that try-except blocks will look like this:
    try:
        some code
    except PauseError:
        #pass it on to the next level to exit out of any loops
        raise PauseError
    except someUndesiredButPredictableError as e:
        logger.error('An exception occurred here because of bad user input or lost TCP connection or something.  This can be fixed without restarting the program.\n'+str(e))
        raise PauseError
    except Exception as e:
        logger.error('An exception occurred, and we don't know what to do about it.\n'+str(e))
    If general Exceptions are not caught, then unexpected Exceptions will cause the code to stop and the error will be reported by the default mechanism.
    """
    pass

def setup_log():
    """This function sets up the error logging to both console and file.  Logging should be set up at the top of each
    file by doing:
    import logging
    logger = logging.getLogger(__name__)
    """

    #logging.basicConfig(filename='log.txt',filemode='a',format='%(asctime)s %(threadName)s %(filename)s %(funcName) %(lineno) %(levelname)s %(message)s', datefmt='%Y/%m/%d %H:%M:%S')

    #get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    #set up logging to console for INFO and worse
    sh = colorlog.StreamHandler()
    sh.setLevel(logging.INFO)
    #sh_formatter = colorlog.Formatter(fmt='%(log_color)s%(levelname):%(asctime)s\n%(message)s', datefmt='%H:%M:%S')
    sh_formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(levelname)-8s - %(name)-25s - %(threadName)-15s - %(asctime)s - %(cyan)s \n  %(message)s\n",
    datefmt=None,
    reset=True,
    log_colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'red,bg_white',
    },
    secondary_log_colors={},
    style='%'
)
    sh.setFormatter(sh_formatter)

    #set up logging to file for ALL messages
    #fh = logging.FileHandler('log.txt')
    # fh = logging.handlers.TimedRotatingFileHandler('log.txt', when='midnight', interval=1, backupCount=7)
    # fh.setLevel(logging.DEBUG)
    # fh_formatter = logging.Formatter(fmt='%(asctime)s.%(msecs)03d - %(threadName)s - %(filename)s.%(funcName)s.%(lineno)s - %(levelname)s\n%(message)s\n\n', datefmt='%Y/%m/%d %H:%M:%S')
    # fh.setFormatter(fh_formatter)

    #put the handlers to use
    logger.addHandler(sh)
    # logger.addHandler(fh)