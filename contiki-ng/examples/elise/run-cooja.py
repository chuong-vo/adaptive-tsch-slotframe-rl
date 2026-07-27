#!/usr/bin/env python3

import sys
import os
import argparse
from subprocess import Popen, PIPE, STDOUT, CalledProcessError

# contiker bash -c 'cd examples/benchmarks/rl-sdwsn && ./run-cooja.py'

# get the path of this example
SELF_PATH = os.path.dirname(os.path.abspath(__file__))
# move three levels up
CONTIKI_PATH = os.path.dirname(os.path.dirname(SELF_PATH))

COOJA_PATH = os.path.normpath(os.path.join(CONTIKI_PATH, "tools", "cooja"))
cooja_output = 'COOJA.testlog'
cooja_log = 'COOJA.log'

#######################################################
# Run a child process and get its output


def run_subprocess(args, input_string):
    retcode = -1
    stdoutdata = ''
    try:
        proc = Popen(args, stdout=PIPE, stderr=STDOUT, stdin=PIPE,
                     shell=True, universal_newlines=True)
        (stdoutdata, stderrdata) = proc.communicate(input_string)
        if not stdoutdata:
            stdoutdata = '\n'
        if stderrdata:
            stdoutdata += stderrdata + '\n'
        retcode = proc.returncode
    except OSError as e:
        sys.stderr.write("run_subprocess OSError:" + str(e))
    except CalledProcessError as e:
        sys.stderr.write("run_subprocess CalledProcessError:" + str(e))
        retcode = e.returncode
    except Exception as e:
        sys.stderr.write("run_subprocess exception:" + str(e))
    finally:
        return (retcode, stdoutdata)

#############################################################
# Run a single instance of Cooja on a given simulation script


def execute_test(cooja_file):
    # cleanup
    try:
        os.remove(cooja_output)
    except FileNotFoundError as ex:
        pass
    except PermissionError as ex:
        print("Cannot remove previous Cooja output:", ex)
        return False

    try:
        os.remove(cooja_log)
    except FileNotFoundError as ex:
        pass
    except PermissionError as ex:
        print("Cannot remove previous Cooja log:", ex)
        return False

    filename = os.path.join(SELF_PATH, cooja_file)
    args = " ".join(["cd", COOJA_PATH, "&&", "sudo ./gradlew run --args='-nogui=" +
                    filename, "-contiki=" + CONTIKI_PATH+" -logdir="+SELF_PATH+" -logname=COOJA"+"'"])
    sys.stdout.write("  Running Cooja, args={}\n".format(args))

    (retcode, output) = run_subprocess(args, '')
    if retcode != 0:
        sys.stderr.write("Failed, retcode=" + str(retcode) + ", output:")
        sys.stderr.write(output)
        return False

    sys.stdout.write("  Checking for output...")

    is_done = False
    with open(cooja_output, "r") as f:
        for line in f.readlines():
            line = line.strip()
            if line == "TEST OK":
                sys.stdout.write(" done.\n")
                is_done = True
                continue

    if not is_done:
        sys.stdout.write("  test failed.\n")
        return False

    sys.stdout.write(" test done\n")
    return True

#######################################################
# Run the application


def main():

    parser = argparse.ArgumentParser(
        description='This script runs the given CSC simulation file.')

    parser.add_argument('file', type=str,
                        help="Simulation file (csc)")

    args = parser.parse_args()
    input_file = args.file

    if not os.access(input_file, os.R_OK):
        print('Simulation script "{}" does not exist'.format(input_file))
        exit(-1)

    print('Using simulation script "{}"'.format(input_file))
    if not execute_test(input_file):
        exit(-1)

#######################################################


if __name__ == '__main__':
    main()
