#!/bin/bash

# Step 1: Create the virtual environment using the exact Python path
/c/Python38-32/python.exe -m venv .venv

# Step 2: Install dependencies using the pip from the venv Scripts folder
# We do NOT activate the venv — instead, we directly call pip from the venv
./.venv/Scripts/pip.exe install -r requirements.txt
