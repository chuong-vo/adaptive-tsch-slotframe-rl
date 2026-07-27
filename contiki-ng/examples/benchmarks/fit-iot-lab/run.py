import os
from os import chdir as cd
from tkinter import COMMAND

ARCH_PATH = "../../../arch"
APP_DIR = "../../hello-world"

TARGET = "iotlab"
BOARD = "m3"

cd("../../hello-world")

COMMAND = "ARCH_PATH="+ARCH_PATH+" make TARGET=" + \
    TARGET+" BOARD="+BOARD+" savetarget"

print(COMMAND)

COMMAND2 = "ARCH_PATH="+ARCH_PATH+" make "

print(COMMAND2)


os.system(COMMAND)
os.system(COMMAND2)
