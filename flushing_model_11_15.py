# -*- coding: utf-8 -*-
"""
Created on Fri Nov  6 20:59:26 2026

@author: hsche
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd



def add_season(ds, flow_col):
    # label each day as wet (top 1/3 of inflows) or  dry (bottom 1/3) 
    dry_limit = ds[flow_col].quantile(1/3)
    wet_limit = ds[flow_col].quantile(2/3)
    season = []
    for flow in ds[flow_col]:
        if flow >= wet_limit:
            season.append('wet')
        elif flow <= dry_limit:
            season.append('dry')
        else:
            season.append('mid')
    ds['Season'] = season
    return ds

# I deleted the other data imports, we can always add them back if we want to compare different data

## Imported Data from Meekong river commision
ds_mrc = pd.read_csv('mrc_luang_data.csv')

ds_mrc['Timestamp'] = pd.to_datetime(ds_mrc['Timestamp'].str[:10], errors='coerce')
ds_mrc = ds_mrc.groupby("Timestamp", as_index = False)['Value'].mean()
ds_mrc = add_season(ds_mrc, 'Value')
exact_dates = list(ds_mrc['Timestamp'])
inflow_data = ds_mrc['Value']
season_data = list(ds_mrc['Season'])


# select dates
date_start=str(exact_dates[0])
year_start=int(date_start[:4])
date_end=str(exact_dates[-1])
year_end=int(date_end[:4])


# plot inflow plot
days=np.linspace(year_start,year_end,len(inflow_data))
plt.plot(days,inflow_data)
plt.title('Inflow Data over Time')
plt.xlabel('Time (years)')
plt.ylabel('Inflow (m^3/s)')

# model dam
min_level=278 # meters
max_level=298 # meters
storage= 1300000000 # m^3 (changed based on online resources)
turb_capacity = 5000 # m^3/s (changed based on online resources)
flush_capacity = 3980 #m^3/s
area_reservoir = storage/max_level
max_storage = storage
constant_max_storage = storage
min_storage=area_reservoir*min_level
seconds_in_day = 60*60*24
seconds_in_hour = 60*60
max_power = 1289 #MW
design_head = 18.9 #m
operating_level = max_level # m, level the dam tries to hold the reservoir at
tailwater_level = min_level - design_head
live_fraction = .2 #fraction of resevoir where build up will effect head (i.e. not at the very base of the dam)


#sediment parameters, mostly placeholders until we can properly parameterize
sed_load = 100*10**6 # T/year #sourced from a paper (Xun Chua et al 2024)
bulk_density = 1.3 #t/m^3
sluice_reduction = 0.3 #30% reduction
flushed_goal = 0.3 # fraction of the sediment in the reservoir to flush out each flush season
flush_concentration = 0.02 # t/m^3, sediment carried per m^3 of flushing water (source needed)
#dredge_fraction = 0.8 #maybe move to seperate dreging model

# monetary parameters
electricty_price = 64 #$/MWh
sluice_cost = 2*10**6 #$/Year
flush_cost = 0.3
#dredge_cost = 5 #$/m^3


#create functions for the various sediment stratagies

def TE(capacity, annual_inflow):
    R = capacity/annual_inflow
    te = R/(0.012+1.02*R)
    return te

def bau(TE, sed_vol):
    #business as usual, costs nothing but lets sediment acccumlate
    dv = TE*sed_load/bulk_density #accumulated sediment
    cost = 0
    return sed_vol + dv, cost

def flushing(TE, sediment_vol):
    # sediment builds up the same as BAU here; the actual flushing happens
    # inside run_dam during the chosen flush season (turbines off while flushing)
    dv = TE*sed_load/bulk_density
    cost = 0 # flushing cost is added inside run_dam for each m^3 flushed
    return sediment_vol + dv, cost
'''
def dredging(TE, sediment_vol):
    # a fixed volume is dredged out each year
    dv = TE*sed_load/bulk_density
    sediment_vol = sediment_vol + dv
    removed = dredge_fraction*dv
    if removed > sediment_vol:   # can't dredge more than existing amount of seds
        removed = sediment_vol
    cost = removed*dredge_cost
    return sediment_vol - removed, cost
'''



def run_dam(ts, flow_data, season_data, sed_strat, flush_season):
    #ts is time_step so we can experiment with appropriate timesteps given dam fills very quickly
    #flush_season is wet or dry, the season flushing happens in
    flow_data = list(flow_data)
    ts_sec = ts * seconds_in_hour # seconds in timestep
    steps_day = int(24/ts) #steps in a day
    steps_year = 365 * steps_day
    steps = len(flow_data)* steps_day

    max_storage = storage
    min_storage = area_reservoir *min_level
    sediment_vol = 0

    # flushing toggle variables
    flushed_yet = False  # set to false at the begining
    vol_flushed = 0      # m^3 of sediment flushed so far this season
    flush_target = 0     # m^3 of sediment to flush this season
    if flush_season == 'wet':
        other_season = 'dry'
    else:
        other_season = 'wet'

    ##initialize lists
    # Although there was not a reservoir in 1984 we will
    # imagine that the reservoir starts at minimum storage
    s_lis = [min_storage] #m^3
    energy_lis = [0] #MW-hour
    tot_discharge_lis=[0] #m^3
    turbine_water_lis=[0] #m^3
    turbine_time_lis=[0] #hour
    spillway_lis=[0] #m^3 includes the water released through the flushing gates
    capacity_lis=[]
    cost_lis = []
    flush_hours_lis = [] #hours spent flushing each year
    sed_vol_flushed = []
    sed_vol_lis = [0]
    last_index = 0

    for j in range(steps - 1):
        day = (j+1)//steps_day
        # still tackle sediment once per year, but for multiple days
        if j % steps_year ==0:
            annual_inflow = sum(flow_data[day:day+365])*seconds_in_day
            te = TE(storage - sediment_vol, annual_inflow)
            sediment_vol, cost = sed_strat(te, sediment_vol)
            # only part of the sediment fills up in the "live" area
            max_storage = constant_max_storage - sediment_vol*live_fraction
            #if max_storage < min_storage:     # live storage completely full of sediment
                #max_storage = min_storage
            capacity_lis.append((storage - sediment_vol)/(10**6))
            cost_lis.append(cost)
            flush_hours_lis.append(0)
        level = s_lis[-1]/area_reservoir
        head = level - tailwater_level
        if head<0:
            head=0
        head_ratio = min(head/design_head, 1)
        target_storage = min(area_reservoir*operating_level, max_storage) # can't hold above what sediment allows

        # add inflow to storage from previous day
        imagined_storage=flow_data[day]*ts_sec+s_lis[-1]

        # decide whether to flush this time step, kinda like the first toggle
        #but ensures you can have multiple flushing days
        flushing_now = False
        if sed_strat == flushing:
            if season_data[day] == flush_season:
                if flushed_yet == False:
                    if vol_flushed == 0: # start of this season's flush, set the goal
                        flush_target = flushed_goal*sediment_vol #flush goal is a percentage, this gives the actual amount of sediment
                    if vol_flushed < flush_target:
                        flushing_now = True #second toggle remains true to keep flushing
                    else:
                        flushed_yet = True # first toggle on so there'sno more flushing this season
                        last_index = day
            elif season_data[day] == other_season:
                # opposite season has arrived, so toggle turns on so we can flush again next flush season 
                vol_flushed = 0
                flushed_yet = False
        # model the flushing
        if flushing_now and day-last_index>200:
            # flushing gates open: all water above min level leaves through them
            flush_water = ts_sec*flush_capacity
            #flush_water = imagined_storage-min_storage
            if flush_water < 0:
                flush_water = 0
            spill=0
            if flush_water < imagined_storage-target_storage:
                spill = imagined_storage-target_storage-flush_water
            elif flush_water > imagined_storage-target_storage:
                flush_water = imagined_storage-target_storage
            flushed = flush_concentration*flush_water/bulk_density # m^3 of sediment carried out
            if flushed > sediment_vol: # can't flush more than is there
                flushed = sediment_vol
            sed_vol_flushed.append(flushed)
            sediment_vol = sediment_vol - flushed
            if sediment_vol<0:
                sediment_vol=0
            vol_flushed = vol_flushed + flushed
            cost_lis[-1] = cost_lis[-1] + flushed*flush_cost
            flush_hours_lis[-1] = flush_hours_lis[-1] + ts
            # less sediment means more live storage again
            max_storage = constant_max_storage - sediment_vol*live_fraction
            if max_storage < min_storage:
                max_storage = min_storage
            energy_lis.append(0)
            turbine_water_lis.append(0)
            turbine_time_lis.append(0)
            spillway_lis.append(flush_water) #all of the flushed water goes to the spillway
            tot_discharge=flush_water+spill
            tot_discharge_lis.append(tot_discharge)
        elif imagined_storage>target_storage:
            #can release water through turbines to get power
            sed_vol_flushed.append(0)
            poss_turb_vol = imagined_storage-target_storage #possible volume through turbines
            poss_turb_sec = poss_turb_vol/turb_capacity #possible run time of turbines
            if poss_turb_sec>=ts_sec:
                #turbine runs the whole day, any remaining water must be lost through spillways
                turb_time = ts_sec
                turbine_time_lis.append(ts_sec/seconds_in_hour)
                turb_water=turb_time*turb_capacity
                turbine_water_lis.append(turb_water)
                remaining_water=imagined_storage-turb_water
                if remaining_water>max_storage: #must release water through spillway
                    spill=remaining_water-max_storage
                else: #water level is below maximum line after turbines run, no need for spill
                    spill=0
                spillway_lis.append(spill)
                #calculate energy
                energy=max_power*turb_time/seconds_in_hour*head_ratio
            else: # turbine runs less than full day and no need to lose water through spillways
                spill=0
                spillway_lis.append(spill)
                turb_time=poss_turb_sec # as calculated above
                turbine_time_lis.append(turb_time/seconds_in_hour)
                turb_water=poss_turb_vol
                turbine_water_lis.append(turb_water)
                # calculate energy
                energy=max_power*turb_time/seconds_in_hour*head_ratio
            energy_lis.append(energy)
            tot_discharge=spill+turb_water
            tot_discharge_lis.append(tot_discharge)
        else: # imagined_storage<=target_storage
            sed_vol_flushed.append(0)
            energy = 0
            energy_lis.append(energy)
            tot_discharge=0
            tot_discharge_lis.append(tot_discharge)
            turbine_water_lis.append(0)
            turbine_time_lis.append(0)
            spillway_lis.append(0)

        new_storage = imagined_storage-tot_discharge
        if new_storage>constant_max_storage:
            print('Something is wrong! New storage cannot exceed maximum storage')
        s_lis.append(new_storage)
        sed_vol_lis.append(sediment_vol)

    #sum each year's energy and profits
    annual_energy_lis = []
    revenue_lis = []
    profit_lis = []
    for y in range(len(capacity_lis)):
        start = 1 + y*steps_year
        y_energy = sum(energy_lis[start: start+steps_year])
        revenue = y_energy*electricty_price
        annual_energy_lis.append(y_energy)
        revenue_lis.append(revenue)
        profit_lis.append(revenue - cost_lis[y])

    #combine everything into a dictionary for efficiency purposes
    results = {'storage': s_lis,                   #per ts
               'energy': energy_lis,               #per ts
               'discharge': tot_discharge_lis,     #per ts
               'turbine_water': turbine_water_lis, #per ts
               'turbine_time': turbine_time_lis,   #per ts
               'spillway': spillway_lis,           #per ts
               'sed_flushed' : sed_vol_flushed,    #per ts
               'sed_volume' : sed_vol_lis,         #per ts
               'capacity': capacity_lis,           #per yr
               'annual_energy': annual_energy_lis, #per yr
               'cost': cost_lis,                   #per yr
               'revenue': revenue_lis,             #per yr
               'profit': profit_lis,               #per yr
               'flush_hours': flush_hours_lis}     #per yr
    return results

time_step = 1
strategies = [bau, flushing, flushing]
names = ['BAU', 'Flushing (wet season)', 'Flushing (dry season)']
flush_seasons = ['wet', 'wet', 'dry'] # only matters for the flushing runs

fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
for i in range(len(strategies)):
    results = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
    years = np.arange(len(results['capacity'])) + year_start

    ax1.plot(years, results['capacity'], label=names[i])
    ax2.plot(years, np.array(results['annual_energy'])/1000, label=names[i])  # GWh
    ax3.plot(years, np.array(results['profit'])/1e6, label=names[i])          # million $

    print(names[i])
    print('  final capacity:', round(results['capacity'][-1]), 'Mm^3')
    print('  total energy:  ', round(sum(results['annual_energy'])/1000), 'GWh')
    print('  total cost:    ', round(sum(results['cost'])/1e6, 1), 'million $')
    print('  total profit:  ', round(sum(results['profit'])/1e6, 1), 'million $')
    print('  avg ann energy ', round(np.mean(results['annual_energy'])/1000,1), 'GWh')
    print('  avg flush time ', round(np.mean(results['flush_hours'])/24,1), 'days/yr')
    print('  max flush time ', round(np.max(results['flush_hours'])/24,1), 'days/yr')
    
    

ax1.set_ylabel('Capacity (Mm$^3$)')
ax1.set_title('Reservoir Capacity')
ax1.legend()
ax2.set_ylabel('Energy (GWh/yr)')
ax2.set_title('Annual Energy Production')
ax3.set_ylabel('Profit (million $/yr)')
ax3.set_title('Annual Profit (energy revenue - sediment cost)')
ax3.set_xlabel('Year')
plt.tight_layout()
plt.show()
'''
# now look at different percentages for dry and wet season and how it impacts the number of days
max_dry_days = []
max_wet_days = []
max_days_season = [0, max_wet_days, max_dry_days]
avg_dry_days = []
avg_wet_days = []
avg_days_season = [0, avg_wet_days, avg_dry_days]
min_dry_days = []
min_wet_days = []
min_days_season = [0, min_wet_days, min_dry_days]

#looking at average, minimum, and maximum days of flushing at different percentages for wet and dry season
percent_removed = np.linspace(0,0.9,20)
fig2, (axis1, axis2, axis3) = plt.subplots(3,1, figsize=(10,10))
for p in percent_removed:
    flushed_goal = p
    for i in range(1, len(strategies)):
        results = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
        hours_flush = results['flush_hours']
        if sum(hours_flush) != 0:
            hours_flush = [x for x in hours_flush if x!=0]
        max_days_season[i].append(np.max(results['flush_hours'])/24)
        avg_days_season[i].append(np.mean(results['flush_hours'])/24)
        min_days_season[i].append(np.min(hours_flush)/24)
print(avg_days_season[1])
print(avg_days_season[2])

for i in range(1, len(strategies)):
    axis1.scatter(percent_removed, max_days_season[i], label=names[i])
    axis2.scatter(percent_removed, avg_days_season[i], label=names[i])
    axis3.scatter(percent_removed, min_days_season[i], label=names[i])

axis1.set_ylabel('Maximum Flush Time (days)')
axis1.set_title('Maximum Days Spent Flushing')
axis1.legend()
axis2.set_ylabel('Average Flush Time (days)')
axis2.set_title('Average Days Spent Flushing')
axis3.set_ylabel('Minimum Flush Time (days)')
axis3.set_title('Minimum Days Spent Flushing')
axis3.set_xlabel('Percent ot Total Sediment Removed')
plt.tight_layout()
plt.show()
'''
'''
# looking at energy production for different percentages over dry and wet season
dry_avg_energy = []
wet_avg_energy = []
avg_energy_season = [0, wet_avg_energy, dry_avg_energy]
dry_profit = []
wet_profit = []
profit_season = [0, wet_profit, dry_profit]
percent_removed = np.linspace(0,0.9,20)
percent_removed = percent_removed[1:]
fig2, (axis1, axis2) = plt.subplots(2,1, figsize=(10,10))
for p in percent_removed:
    flushed_goal = p
    for i in range(1, len(strategies)):
        results = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
        avg_energy_season[i].append(np.mean(results['annual_energy']))
        profit_season[i].append(sum(results['profit'])/1e6)
for i in range(1, len(strategies)):
    axis1.scatter(percent_removed, avg_energy_season[i], label=names[i])
    axis2.scatter(percent_removed, profit_season[i], label=names[i])
axis1.legend()
axis1.set_ylabel('Energy (GWh/yr)')
axis1.set_title('Annual Energy Production')
axis2.set_ylabel('Profit (million $/yr)')
axis2.set_title('Annual Profit (energy revenue - sediment cost)')
axis2.set_xlabel('Percent ot Total Sediment Removed')
plt.tight_layout()
plt.show()

# now I want to look at specific time periods 
# plotting sediment release
flushed_goal = 0.2
plt.figure()
for i in range(1, len(strategies)):
    steps=np.linspace(year_start,year_end,len(inflow_data)*24)
    r = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
    steps=steps[300000:350000]
    sed=r['sed_flushed']
    sed=sed[300000:350000]
    plt.plot(steps, sed, label=names[i])
plt.xlabel('Years')
plt.ylabel('Volume of Flushed Sediment (m^3)')
plt.legend()
plt.title(f'Flushed Sediment {flushed_goal*100}% Removal')
plt.show()

#plotting power production
plt.figure()
for i in range(1, len(strategies)):
    steps=np.linspace(year_start,year_end,len(inflow_data)*24)
    r = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
    steps=steps[300000:350000]
    energy=r['energy']
    energy=energy[300000:350000]
    plt.plot(steps, energy, label=names[i])
plt.xlabel('Years')
plt.ylabel('Energy (GWh/yr)')
plt.legend()
plt.title(f'Power Production {flushed_goal*100}% Removal')
plt.show()

# trying to figure out why sediment volume isn't changing
plt.figure()
percent_removed = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
for i in range(1, len(strategies)-1):
    for p in percent_removed:
        flushed_goal=p
        results = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
        #years = np.arange(len(results['capacity'])) + year_start
        steps=np.linspace(year_start,year_end,len(inflow_data)*24)
        sed = results['sed_volume']
        plt.plot(steps, sed, label=f'{p*100}%')
        
plt.xlabel('Years')
plt.ylabel('Stored Sediment (m^3)')
plt.legend()
plt.title('Sediment Volume over Time')
plt.show()
'''

# create parallel coordinate plot
import pandas as pd 
from pandas.plotting import parallel_coordinates
import matplotlib.cm as cm
from matplotlib.lines import Line2D

percent_removed = list(np.linspace(0.1,0.9,9))
sed_volume = []
avg_days_flush = []
profit = []
sed_flushed = []

for i in range(1, len(strategies)):
    for p in percent_removed:
        flushed_goal=p
        #print(flushed_goal, flush_seasons[i])
        results = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
        avg_days_flush.append(np.mean(results['flush_hours'])/24)
        sed_volume.append(np.mean(results['sed_volume']))
        profit.append(np.mean(results['profit']))
        sed_flushed.append(np.mean(results['sed_flushed']))
neg_sed_volume = [-x for x in sed_volume]
neg_avg_days_flush=[-x for x in avg_days_flush]
seasons = []
for i in range(len(percent_removed)):
    seasons.append('Wet')
for i in range(len(percent_removed)):
    seasons.append('Dry')

percents = percent_removed + percent_removed
df = pd.DataFrame({
    'Season' : seasons,
    'Percent' : percents,
    'Rev_Days' : neg_avg_days_flush,
    'Rev_Sed_Volume' : neg_sed_volume,
    'Sed_Flushed' : sed_flushed,
    'Profit' : profit
    })
#scale
metrics = ['Rev_Days', 'Rev_Sed_Volume', 'Profit', 'Sed_Flushed']
df_scaled = df.copy()
df_scaled[metrics] = (df[metrics]-df[metrics].min())/(df[metrics].max()-df[metrics].min())
df_scaled['Label'] = (
    df_scaled['Season'] + ' ' + df_scaled['Percent'].astype(str) + '%'
)
 #figure out colors
wet_shades = cm.Blues(np.linspace(0.3,1.0, len(percent_removed)))
dry_shades = cm.Reds(np.linspace(0.3,1.0, len(percent_removed)))
colors = list(wet_shades) + list(dry_shades)
# plot
plt.figure(figsize=(8,5))
parallel_coordinates(
    frame=df_scaled,
    class_column='Label',
    cols=metrics,
    color = colors,
    linewidth = 2,
    alpha = 0.8
    )

legend_handles = [
    Line2D([0], [0], color=cm.Blues(0.75), lw=2.5, label='Wet (10% → 90%)'),
    Line2D([0], [0], color=cm.Reds(0.75), lw=2.5, label='Dry (10% → 90%)'),
]
plt.legend(handles=legend_handles, title='Season', loc='best')

plt.title('Wet vs. Dry Season based on Sediment Reduction')
plt.ylabel('Normalized Value (0=Min, 1=Max')
plt.grid(True, alpha=0.3)
plt.show()

# create parallel plot for days
max_days_flush = []
avg_days_flush = []
min_days_flush = []

for i in range(1, len(strategies)):
    for p in percent_removed:
        flushed_goal=p
        #print(flushed_goal, flush_seasons[i])
        results = run_dam(time_step, inflow_data, season_data, strategies[i], flush_seasons[i])
        max_days_flush.append(np.max(results['flush_hours'])/24)
        avg_days_flush.append(np.mean(results['flush_hours'])/24)
        min_days_flush.append(np.min(results['flush_hours'])/24)

seasons = []
for i in range(len(percent_removed)):
    seasons.append('Wet')
for i in range(len(percent_removed)):
    seasons.append('Dry')

percents = percent_removed + percent_removed
df = pd.DataFrame({
    'Season' : seasons,
    'Percent' : percents,
    'Max_Days' : max_days_flush,
    'Avg_Days' : avg_days_flush,
    'Min_Days' : min_days_flush,
    })
#scale
metrics = ['Max_Days', 'Avg_Days', 'Min_Days']
df['Label'] = (
    df['Season'] + ' ' + df['Percent'].astype(str) + '%'
)
 #figure out colors
wet_shades = cm.Blues(np.linspace(0.3,1.0, len(percent_removed)))
dry_shades = cm.Reds(np.linspace(0.3,1.0, len(percent_removed)))
colors = list(wet_shades) + list(dry_shades)
# plot
plt.figure(figsize=(8,5))
parallel_coordinates(
    frame=df,
    class_column='Label',
    cols=metrics,
    color = colors,
    linewidth = 2,
    alpha = 0.8
    )

legend_handles = [
    Line2D([0], [0], color=cm.Blues(0.75), lw=2.5, label='Wet (10% → 90%)'),
    Line2D([0], [0], color=cm.Reds(0.75), lw=2.5, label='Dry (10% → 90%)'),
]
plt.legend(handles=legend_handles, title='Season', loc='best')

plt.title('Wet vs. Dry Season based on Sediment Reduction')
plt.ylabel('Normalized Value (0=Min, 1=Max')
plt.grid(True, alpha=0.3)
plt.show()





  


    



    