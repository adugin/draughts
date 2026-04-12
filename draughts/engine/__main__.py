"""Entry point for ``python -m draughts.engine``.

Starts an interactive engine session reading commands from stdin and
writing responses to stdout.

Sample session::

    $ python -m draughts.engine
    uci
    id name DRAUGHTS-engine
    id author Andrey Dugin
    option name Hash type spin default 64 min 1 max 1024
    option name Threads type spin default 1 min 1 max 1
    option name Level type spin default 4 min 1 max 6
    option name MoveTime type spin default 3000 min 100 max 60000
    udriok
    isready
    readyok
    position startpos
    go depth 4
    info depth 1 score cp 0 nodes 12 nps 12000 time 1 pv c3-d4
    info depth 2 score cp 0 nodes 45 nps 22500 time 2 pv c3-d4
    info depth 3 score cp 20 nodes 210 nps 70000 time 3 pv c3-d4
    info depth 4 score cp 15 nodes 890 nps 89000 time 10 pv c3-d4
    bestmove c3-d4
    quit
"""

from draughts.engine import run_engine_main

if __name__ == "__main__":
    run_engine_main()
