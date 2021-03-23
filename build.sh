#!/usr/bin/env bash

docker build -t clouddrove/aws-secret:1.0 .

if [[ $? != 0 ]]; then
    echo "aws secret docker Build failed."
    exit 1
fi

docker push clouddrove/aws-secret:1.0
