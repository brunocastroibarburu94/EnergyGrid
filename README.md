# Energy Grid

This repository contains a small demonstration of a tool that automatically calls the APIs from [National Grid](https://carbon-intensity.github.io/api-definitions/?python#carbon-intensity-api-v2-0-0) and [Imperial College London](https://electricitycosts.org.uk/api-documentation/) to retrieve information about the CO2 intensity and price of electricity per kWh.

# Running Locally #
This software suite is designed to be able to run locally in any operative system (Windows/MacOS/Linux) and also be able to be deployed in the web.

### Recommended Software ###
- Docker (all OS): The application will be run in docker containers
- GitBash (For windows): Useful command line for Windows users that allows you to run bash scripts (the ones ending in .sh).

### How to Run Locally ###
1. create your own local_container.sh from local_container.sh.template as the bash script to initialize the container (Mild modifications may be needed for MacOS or Linux)
1. Make use of the Makefile

```bash
# Execute local container
. local_container.sh
```

```bash
# Install libraries to develop locally
make run
```
