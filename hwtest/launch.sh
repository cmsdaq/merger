#!/bin/bash

## Source this script to launch the merging test

LIST_PRODUCERS=listProducers.txt
#LIST_MERGERS=listMergers.txt
LIST_MERGERS=$LIST_PRODUCERS
ALL_NODES=all_nodes.txt

LUMI_LENGTH_MEAN=9.0
LUMI_LENGTH_SIGMA=9.0

## Top-level directory for the test management and control
MASTER_BASE=/hwtests/master
## Top level directory for the producer and merger scripts used during the test
SLAVE_BASE=/hwtests/slave
## Folder for the producer inputs
#FROZEN_BASE=/home/cern/frozen # HDD
FROZEN_BASE=/fff/ramdisk/hwtest/frozen # RAM disk
## Top-level directory for the producer outputs / merger inputs
#INPUT_BASE=/mnt/cmsfs/benchmark/inputs # Lustre
INPUT_BASE=/fff/ramdisk/hwtest/inputs # RAM disk
## Top-level directory for the merger outputs
OUTPUT_BASE=/mnt/cmsfs/benchmark

## Provides node_name, count_args, parse_machine_list, echo_and_ssh
source $MASTER_BASE/hwtest/tools.sh

#-------------------------------------------------------------------------------
function launch_main {
    echo "+ Launching the test ..."
    clean_up
    launch_merger 100 optionC bu-c2d38-27-01 macro
    launch_mergers 100 optionC
    launch_producers run100.cfg 1
    echo "+ ... done. Finished launching the test."
} # launch_main


#-------------------------------------------------------------------------------
function clean_up {
    kill_previous_mergers_and_producers
    delete_previous_runs
    delete_previous_code
} # clean_up


#-------------------------------------------------------------------------------
function delete_previous_runs {
    echo "++ Deleting previous runs ..."
    NODES=$(parse_machine_list $ALL_NODES)
    for NODE in $NODES; do
        COMMAND="rm -rf {$INPUT_BASE,$OUTPUT_BASE}/{,*/}*merge*/run*"
        echo_and_ssh $NODE "$COMMAND"
    done
    printf "++ ... done. Finished deleting previous runs.\n\n"
} # delete_previous_runs


#-------------------------------------------------------------------------------
function delete_previous_code {
    echo "++ Delete previous code ..."
    NODES="$(parse_machine_list $ALL_NODES)"
    for NODE in $NODES; do
        COMMAND="rm -rf $SLAVE_BASE"
        echo_and_ssh $NODE "$COMMAND"
    done
    printf "++ ... done. Finished deleting previous code.\n\n"    
} # delete_previous_code


#-------------------------------------------------------------------------------
function kill_previous_mergers_and_producers {
    echo "++ Killing previous mergers and producers ..."
    NODES="$(parse_machine_list $ALL_NODES)"
    for NODE in $NODES; do
        COMMAND="$(cat <<'EOF'
            PROCESS_IDS=$(ps awwx |\
                egrep "dataFlowMergerInLine|manageStreams.py" |\
                egrep -v "grep|bash" |\
                awk '{print $1}');\
            if [[ ! -z "$PROCESS_IDS" ]]; then                              \
                kill -9 $PROCESS_IDS                                       ;\
            fi
EOF
            )"
        echo_and_ssh $NODE "$COMMAND"
    done
    printf "++ ... done. Finished killing previous mergers and producers.\n\n"
} # kill_previous_mergers_and_producers


#-------------------------------------------------------------------------------
# Expects the run number as the first argument,
# the merging option as the second one
function launch_mergers {
    echo "++ Launching mergers ..."
    RUN=${1:-300}
    OPTION=${2:-OptionA}
    for NODE in $(parse_machine_list $LIST_MERGERS); do
        launch_merger $RUN $OPTION $NODE mini
    done
    printf "++ ... done. Finished launching mergers.\n\n"
} # launch_mergers


#-------------------------------------------------------------------------------
# Expects the run number as the first argument,
# the merging option as the second one
# the node name as the third one
function launch_merger {
    RUN=${1:-300}
    THEOPTION=${2:-OptionA}
    NODE=${3:-}
    MODE=${4:-mini}
    if [ -z $NODE ]; then
        echo "launch_merger: ERROR: no target host name specified\!"
        return 1
    fi

    MERGER_BASE=$SLAVE_BASE/$NODE/$MODE

    ## Create a custom config file
    CONFIG=$MASTER_BASE/dataFlowMerger.conf
    /bin/cp $MASTER_BASE/dataFlowMergerTemplate.conf $CONFIG
    LCONFIG=$MASTER_BASE/logFormat.conf
    /bin/cp $MASTER_BASE/logFormatTemplate.conf $LCONFIG

    if [ $MODE == "mini" ]; then
        sed -e "s|AAA|$INPUT_BASE/${NODE}/unmergedDATA/run${RUN}|" \
            -e "s|BBB|$INPUT_BASE/${NODE}/unmergedMON|"            \
            -e "s|OPTION|$THEOPTION|"                              \
            -e "s|CCC|$OUTPUT_BASE/mergerMini|"                    \
            -e "s|DDD|$OUTPUT_BASE/mergerMacro|"                   \
            -e "s|LOG|$MERGER_BASE/logFormat.conf|"          \
            -e "s|MODE|mini|"                                      \
            -i $CONFIG
    elif [ $MODE == "macro" ]; then
        sed -e "s|AAA|$OUTPUT_BASE/mergerMini/run${RUN}|"          \
            -e "s|BBB|$OUTPUT_BASE/mergerMacro|"                   \
            -e "s|OPTION|$THEOPTION|"                              \
            -e "s|CCC|$OUTPUT_BASE/mergerMacro|"                   \
            -e "s|DDD|$OUTPUT_BASE/mergerMacro|"                   \
            -e "s|LOG|$MERGER_BASE/logFormat.conf|"          \
            -e "s|MODE|macro|"                                     \
            -i $CONFIG
    else
        echo "launch_merger: ERROR: mode $(quote $MODE) not supported\!"
        echo "                      Expect one of: mini, macro"
        return 1
    fi

    LOG=merger_${THEOPTION}_run${RUN}_${NODE}_${MODE}.log
    sed -e "s|LFILE|$MERGER_BASE/$LOG|" -i $LCONFIG

    ## Make sure that the remote folder to contain source code exists
    ssh $NODE "mkdir -p $MERGER_BASE"

    ## Sync the common source code to the remote node
    rsync -aW $MASTER_BASE/ $NODE:$MERGER_BASE

    ## Customize source code: update hard-cody path to the config file
    mkdir -p $MASTER_BASE/custom
    /bin/cp $MASTER_BASE/{dataFlowMergerInLine,Logging.py} \
        $MASTER_BASE/custom
    
    sed -i "s|dataFlowMerger.conf|$MERGER_BASE/dataFlowMerger.conf|" \
        $MASTER_BASE/custom/{dataFlowMergerInLine,Logging.py}

    ## Sync the custom source code to the remote node
    rsync -aW $MASTER_BASE/custom/ $NODE:$MERGER_BASE

    ## Clean up custom sources
    rm -rf $MASTER_BASE/custom

    ## Create the launch command
    OUT=merger_${THEOPTION}_run${RUN}_${NODE}_${MODE}.out
    COMMAND="$(cat << EOF
    (   cd $OUTPUT_BASE ; \
        nohup $MERGER_BASE/dataFlowMergerInLine \
    )   >& $MERGER_BASE/$OUT &
EOF
    )"
    
    ## Launch the merger
    echo_and_ssh $NODE "$COMMAND" 1
} # launch_merger


#-------------------------------------------------------------------------------
# Expects the config file name as the first argument
# the second argument is to allow for a subdirectory depending on the node
function launch_producers {
    echo "++ Launching producers ..."
    CONFIG=${1:-mergeConfigForReal}
    DOSUBFOLDER=${2:-0}
    TOTALBUS=$(count_args $(parse_machine_list $LIST_PRODUCERS))
    for NODE in $(parse_machine_list $LIST_PRODUCERS); do
        PRODUCER_BASE=$SLAVE_BASE/$NODE/prod
        ssh $NODE "mkdir -p $PRODUCER_BASE"
        rsync -aW $MASTER_BASE/ $NODE:$PRODUCER_BASE/
        SUBFOLDER=""
        if [ ${DOSUBFOLDER} == "1" ]; then
            SUBFOLDER=${NODE}"/"
        fi
        COMMAND="$(cat << EOF
        nohup $PRODUCER_BASE/hwtest/manageStreams.py \
            --config $PRODUCER_BASE/hwtest/$CONFIG \
            --bu $NODE \
            -i $FROZEN_BASE \
            -p $INPUT_BASE/${SUBFOLDER} \
            -a $TOTALBUS \
            --lumi-length-mean=$LUMI_LENGTH_MEAN \
            --lumi-length-sigma=$LUMI_LENGTH_SIGMA \
            >& $PRODUCER_BASE/producer_${CONFIG}_${NODE}.log &
EOF
        )"
        echo_and_ssh $NODE "$COMMAND" 1
    done
    printf "++ ... done. Finished launching producers.\n\n"
} # launch_producers


#-------------------------------------------------------------------------------
function launch_simple_cat {
    ## The number of process per node is passed as the first arg, default=1
    RUN=${1:-300}
    LS=${2:-1}
    NODE=$3
    STREAM=A
    echo $RUN
    SOURCE_BASE=$INPUT_BASE/unmergedDATA/run${RUN}
    DESTINATION_BASE=$OUTPUT_BASE/mergerMini/run${RUN}
    COMMAND="$(cat << EOF
    SOURCES="$SOURCE_BASE/run${RUN}_ls${LS}_Stream${STREAM}_*.dat";
    DESTINATION="$DESTINATION_BASE/run${RUN}_ls${LS}_Stream${STREAM}_SM.dat";
    LOG="$OUTPUT_BASE/cat_${LS}.log";
    rsync -aW $MASTER_BASE/ $NODE:$SLAVE_BASE/;
    (time cat \$SOURCES > \$DESTINATION) >& \$LOG &
EOF
    )"
    echo $NODE
    echo_and_ssh $NODE $COMMAND
    echo
} # launch_simple_cat


#-------------------------------------------------------------------------------
function echo_and_rm {
    if [[ ! -z "$@" ]]; then
        printf "+++ Deleting $@ ..."
        rm -rf $@
        printf " done.\n"
    fi
} ## echo_and_rm

#-------------------------------------------------------------------------------
function quote {
    echo "\`"${@}"'"
} ## quote

launch_main
