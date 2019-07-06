from pyschedule import Scenario, solvers, plotters
from datetime import datetime, date, time, timedelta

import matplotlib
from colorhash import ColorHash

hide_list = []

# Get SO (deadline, qtty, ...)
# Extract Production Orders
# Try to schedule POs


class Fermentation:
    def __init__(self, starting_date=None, fixed_starting_date=None,
                 min_starting_date=None, deadline=None,
                 keg=False, fermentation_days=15, priority=50,
                 title=None):
        pass



begin = date(year=2018, month=8, day=6)
today = date.today()
until = begin + timedelta(days=120)

horizon = (until - begin).days

print("From {0} to {1} ({2} days)".format(begin, until, horizon))

S = Scenario('lss_brewing', horizon=horizon)

# Available fermenters
donkey = S.Resource('ferm.donkey')
diddy = S.Resource('ferm.diddy')
funky = S.Resource('ferm.funky')
dread = S.Resource('ferm.dread')
dixie = S.Resource('ferm.dixie')
kiddy = S.Resource('ferm.kiddy')

fermenters = donkey | diddy | funky | dread | dixie | kiddy

fermenters_all = [donkey, diddy, funky, dread, dixie, kiddy]

# Make sure beer is bottled or transfered to BBT before another fermentation
# starts
for t in range(horizon):
    for fermenter in fermenters_all:
        S += fermenter['block'][:t] <= 1


# brite tanks
cheeta = S.Resource('brite.cheeta')
cheeta2 = S.Resource('brite.cheeta2')
brites_any = cheeta | cheeta2
brites_all = [cheeta, cheeta2]

# for t in range(horizon):
#     for brite in brites_all:
#         S += brite['lock_brite'][:t] <= 1


# Brewhouse
brewhouse = S.Resource('brewhouse')
capper = S.Resource('capper')

chambre_garde = S.Resource('chamber', size=7)

# Staff
gui = S.Resource('staff.guillaume')
pierre = S.Resource('staff.pierre')
val = S.Resource('staff.valentin')
all_staff = (gui, pierre, val)

# Weekends
from dateutil.rrule import DAILY, rrule, SA

def find_saturdays(start_date, end_date):
  return rrule(DAILY, dtstart=start_date, until=end_date, byweekday=(SA))

all_saturdays = find_saturdays(begin, until)

for we_no, saturday in enumerate(all_saturdays):
    We = S.Task(name="We{0}".format(we_no), length=2)
    We += all_staff

    in_days = (saturday.date() - begin).days
    S += We <= in_days+2, We >= in_days

    hide_list.append(We)

# Collect unworkable days from Calendar
# FIXME: Gérer les éléments de plusieurs journées
# FIXME: Gérer les micro événements
print("\t*Collecting calendar days...")
from icalevents.icalevents import events
es  = events("https://calendar.google.com/", start=begin, end=until)
for idx, ev in enumerate(es):
    if "Brassage" not in ev.summary or (ev.start.date() < today):
        if (ev.end.time() <= time(hour=6)) or (ev.start.date() < today):
            print("\t\tConsidered {0} as WORKABLE".format(ev))
        elif (ev.start.date() == ev.end.date()) and (ev.start.time() >= time(hour=16)):
            print("\t\tConsidered {0} as WORKABLE".format(ev))
        else:
            black_day = S.Task(name="BlackDay{0}".format(idx))
            black_day += brewhouse

            in_days = (ev.end.date() - begin).days
            S += black_day <= in_days+1, black_day >= in_days

            print("\t\tMarking {0} as BLACK DAY".format(ev))
    else:
        print("\t\tConsidered {0} as BREWERY SCHEDULED".format(ev))


def make_batch(S, name, fixed_starting_date=None, min_starting_date=None, deadline=None, keg=False, fermentation_days=15, priority=50, title=None):
    brewday = S.Task('{0}_brewday'.format(name))
    brewday.label = title or name

    fermentation = S.Task('{0}_fermentation'.format(name), length=fermentation_days)
    fermentation.block = 1

    fermentation.label = title or name

    maturation = S.Task('{0}_maturation'.format(name), length=21)
    maturation.label = title or name
    maturation += chambre_garde # Stocker en chambre de garde

    if not keg:
        bottling = S.Task('{0}_bottling'.format(name), length=1)
        bottling.label = title or name
        bottling.block = -1
    else:
        transfer_to_brite = S.Task('{0}_to_brite'.format(name), length=1)
        transfer_to_brite.block = -1
        transfer_to_brite.lock_brite = 1
        transfer_to_brite.label = title or name

        brite_carbonation = S.Task('{0}_carbonation'.format(name), length=2)
        brite_carbonation.label = title or name

        kegging = S.Task('{0}_kegging'.format(name), length=1)
        kegging.lock_brite = -1
        kegging.label = title or name

    brewday += {pierre, brewhouse}

    # brewday.schedule_cost = - priority
    # brewday += fermentation # don't ferment if no brewday
    fermentation += fermenters # use any of fermenters

    if not keg:
        # fermentation += bottling # dep
        bottling += {all_staff, fermenters, capper}
        bottling += fermentation * fermenters_all # In case of overlap, use the same fermenter for capping and fermentation
        # bottling += maturation # dep
    else:
        # fermentation += transfer_to_brite # don't transfer if not fermented
        # transfer_to_brite += brite_carbonation # don't carbonate if not transferred
        transfer_to_brite += {brites_any, fermenters} # resources
        transfer_to_brite += fermentation * fermenters_all # use the same fermenter for transfer and fermentation

        brite_carbonation += brites_any
        brite_carbonation += transfer_to_brite * brites_all # use the same brite for carbonation and transfer

        kegging += brites_any
        # kegging += brite_carbonation
        kegging += brite_carbonation * brites_all # use the same fermenter for brite and kegging

    if fixed_starting_date:
        fixed_starting_date_in_future_days = (fixed_starting_date - begin).days
    if min_starting_date:
        min_starting_date_in_future_days = (min_starting_date - begin).days
    if deadline:
        deadline_in_future_days = (deadline - begin).days

    chain = [brewday <= fermentation]

    if fixed_starting_date:
        chain += [brewday > fixed_starting_date_in_future_days, brewday <= fixed_starting_date_in_future_days + 1]

    if min_starting_date:
        chain += [brewday > min_starting_date_in_future_days]

    if keg:
        # chain += [#fermentation < transfer_to_brite,
        chain +=  [fermentation < transfer_to_brite,
                   # (fermentation - transfer_to_brite) < 4,
                   # transfer_to_brite < fermentation + (fermentation.length + 3),
                   transfer_to_brite <= brite_carbonation,
                   brite_carbonation < kegging]
                   # kegging - brite_carbonation < 4]

        # kegging < brite_carbonation + (brite_carbonation.length + 3)] # 5=number of days of slack before kegging

        if deadline:
            chain += [transfer_to_brite < (deadline_in_future_days - 21)] # 21 = maturation time
    else:
        # chain += [#fermentation < bottling,
        chain += [fermentation < bottling,
                  # (fermentation - bottling) < 4,
                  bottling <= maturation] # 5=number of days of slack allowed before bottling
        if deadline:
            chain += [maturation < deadline_in_future_days]

    return chain

# Batches to brew
starting_date = date(2018, 9, 17)

# kegs
# Already produced

S += make_batch(S, "batch_bottle_hopshot", fixed_starting_date=date(2018, 9, 7), deadline=date(2018, 10, 30), title="Bouteilles HopShot")
S += make_batch(S, "batch_bottle_papayou", fixed_starting_date=date(2018, 9, 6), title="Bouteilles Papayou")
S += make_batch(S, "batch_ligne_papayou", fixed_starting_date=date(2018, 8, 31), keg=True, title="Futs Papayou (Lignes div.)")

# Beerstrop
S += make_batch(S, "batch_keg_hs", fixed_starting_date=date(2018, 9, 14), keg=True, deadline=date(2018, 10, 30), title="Futs HopShot Beerstro")
S += make_batch(S, "batch_keg_granivore", fermentation_days=11, keg=True, fixed_starting_date=date(2018, 9, 10), deadline=date(2018, 10, 30), title="Futs Granivore Beerstro")

# TAZ TKT: 7 + 2TS

# S += make_batch("batch_beerstro_granivore", min_starting_date=today, fermentation_days=14, deadline=date(2018, 10, 30), keg=True, priority=100)
# S += make_batch("batch_beerstro_hopshot", min_starting_date=today, deadline=date(2018, 10, 30), keg=True, priority=100)

# # LE BAL
S += make_batch(S, "batch_bal_smoking", min_starting_date=starting_date, deadline=date(2018, 11, 10), keg=True, title="BAL Smoking")
S += make_batch(S, "batch_bal_yoga", min_starting_date=starting_date, fermentation_days=18, deadline=date(2018, 11, 10), keg=True, title="BAL Yoga")
S += make_batch(S, "batch_bal_taz", min_starting_date=starting_date, deadline=date(2018, 11, 10), keg=True, title="BAL TAZ")
S += make_batch(S, "batch_bal_hopshot", min_starting_date=starting_date, deadline=date(2018, 11, 10), keg=True, title="BAL HopShot")

# # LA BICHE
S += make_batch(S, "batch_biche1", min_starting_date=starting_date, deadline=date(2018, 12, 1), keg=True, title="Biche Futs 1")
S += make_batch(S, "batch_biche2", min_starting_date=starting_date, deadline=date(2018, 12, 1), keg=True, title="Biche Futs 2")
S += make_batch(S, "batch_biche3", min_starting_date=starting_date, deadline=date(2018, 12, 1), keg=True, title="Biche Futs 3")

# bottles
## Novembre

# S += make_batch("batch_bottle_pm", deadline=date(2018, 10, 30), priority=0)
S += make_batch(S, "batch_bottle_grani", fermentation_days=11, min_starting_date=starting_date, deadline=date(2018, 11, 10), title="Bouteilles Grani")
S += make_batch(S, "batch_bottle_arctic", min_starting_date=starting_date, deadline=date(2018, 10, 30), title="Bouteilles Papayou")

# ## S += make_batch("batch_bottle_taz", deadline=date(2018, 11, 10), priority=0)

S += make_batch(S, "batch_bottle_hs2", min_starting_date=starting_date, deadline=date(2018, 12, 1), title="Bouteilles Noel HS")
S += make_batch(S, "batch_bottle_taz2", min_starting_date=starting_date, deadline=date(2018, 12, 1), title="Bouteilles Noel TAZ")
S += make_batch(S, "batch_bottle_pm2", min_starting_date=starting_date, deadline=date(2018, 12, 1), title="Bouteilles Noel PapaMex")
S += make_batch(S, "batch_bottle_grani2", fermentation_days=11, min_starting_date=starting_date, deadline=date(2018, 12, 1), title="Bouteilles Noel Grani")
S += make_batch(S, "batch_bottle_arctic2", min_starting_date=starting_date, deadline=date(2018, 12, 1), title="Bouteilles Noel Papayou")

# S += make_batch(S, "batch_bottle_explo1", min_starting_date=today, deadline=date(2018, 12, 1), priority=10, title="Bouteilles Explo1")
# S += make_batch(S, "batch_bottle_explo2", min_starting_date=today, deadline=date(2018, 11, 1), priority=10, title="Bouteilles Explo1")


# Batch colab
# S += make_batch(S, "batch_paparafael", min_starting_date=starting_date, deadline=date(2018, 10, 30), keg=True, priority=100, title="Futs NEIPA Papa Rafa")

S += make_batch(S, "batch_cafecitoyen", min_starting_date=starting_date, deadline=date(2018, 12, 15), keg=True, title="Futs IPA Cafecitoyen")


S.clear_solution()

S.use_makespan_objective()

def make_json(solution):
    events = []

    for idx, sol in enumerate(solution):
        # start_date = datetime.combine(begin + timedelta(sol[2]),
        #                               time(hour=9, minute=0))
        # end_date = datetime.combine(begin + timedelta(sol[3]),
        #                             time(hour=16, minute=0))
        start_date = begin + timedelta(sol[2])
        end_date = begin + timedelta(sol[3])

        if hasattr(sol[0], 'label'):
            title = sol[0].label
        else:
            title = sol[0].name

        events.append({
            'id': "ev-{0}".format(idx),
            'resourceId': sol[1].name,
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'title': title,
            'color': ColorHash(title).hex
        })

    import json
    with open('events.json', 'w') as outfile:
        json.dump(events, outfile)

# A small helper method to solve and plot a scenario
def run(S) :
    if solvers.mip.solve(S, kind="CBC", ratio_gap=1.2, msg=1):
        # if solvers.ortools.solve(S, time_limit=500, msg=1):
        # plotters.matplotlib.plot(S, fig_size=(20, 20), hide_tasks=[] + hide_list, vertical_text=False)
        make_json(S.solution())
    else:
        print('no solution exists')
run(S)


