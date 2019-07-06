from pyschedule import Scenario, solvers, plotters
from datetime import datetime, date, time, timedelta

import matplotlib
from colorhash import ColorHash

hide_list = []

S = Scenario('lss_doubebatch', horizon=60*9)

hlt = S.Resource('hlt')
mt = S.Resource('mt')
bk = S.Resource('bk')

vessels = [hlt, mt, bk]

# Make sure beer is bottled or transfered to BBT before another fermentation
# starts
for t in range(S.horizon):
    S += mt['dirty'][:t] <= 1


def make_brew(name):
    mash = S.Task('mash.{0}'.format(name), length=60)
    mash.dirty = 1
    mash += mt

    sparge1 = S.Task('sparge.{0}.1'.format(name), length=20)
    sparge1 += [mt, bk]

    sparge2 = S.Task('sparge.{0}.2'.format(name), length=20)
    sparge2 += [mt, bk]

    boil = S.Task('boil.{0}'.format(name), length=90)
    boil += bk

    transfer = S.Task('transfer.{0}'.format(name), length=60)
    transfer += bk

    return mash, [mash <= sparge1,
                  sparge1 <= sparge2,
                  sparge2 <= boil,
                  boil <= transfer]


mash1, brew1 = make_brew("A")
S += brew1

mash2, brew2 = make_brew("B")
S += brew2

remove_spent_grain = S.Task('remove_spent_grain', length=20)
remove_spent_grain += mt
remove_spent_grain.dirty = -1

clean_mt = S.Task('clean_mt', length=30)
clean_mt += mt

clean_bk = S.Task('clean_bk', length=40)
clean_bk += bk

S += [mash1 < mash2,
      mash1 < remove_spent_grain,
      mash2 < clean_mt,
      mash2 < clean_bk]

S += [remove_spent_grain < clean_mt,
      remove_spent_grain < clean_bk]

S.clear_solution()

S.use_makespan_objective()

# A small helper method to solve and plot a scenario
def run(S) :
    if solvers.mip.solve(S, kind="CBC", msg=1):
        plotters.matplotlib.plot(S, fig_size=(20, 20), hide_tasks=[] + hide_list, vertical_text=True)
    else:
        print('no solution exists')
run(S)


