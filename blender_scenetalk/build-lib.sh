#!/usr/bin/env bash

rm -rf lib
python3 -m venv .venv
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
cp -rf .venv/lib/python3.11/site-packages lib
