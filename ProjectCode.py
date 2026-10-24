#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Oct 19 13:14:52 2026

@author: isabelseeley
"""
import xarray as xr
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from datetime import datetime
'''
## IMPORTED DATA FROM https://zenodo.org/records/13951712 (What Prof. Galleli gave us)
nc_path = "GRDR_v1.0.0_region_4.nc"
ds = xr.open_dataset(nc_path, chunks={'time': 'auto'})
# reach ID for the region above Xayaburi Dam
target_reach = 44021314
# access data
ds = ds['discharge'].sel(reach=target_reach).to_dataframe().reset_index()
exact_dates1 = list(ds['time'])
inflow_data1 = ds['discharge']
'''

##Import from CSV extracted from grdr
ds = pd.read_csv("Xayaburi_Dam_Inflow.csv")
exact_dates1 = list(ds['time'])
inflow_data1 = ds['discharge']


## IMPORTED DATA FROM https://maps.reachhydro.org/?project=global (has different values for some reason)
ds = pd.read_csv('flow_series.csv')

exact_dates2 = list(ds['Date'])
inflow_data2 = ds['Flow']

## Imported Data from Meekong river commision
ds_mrc = pd.read_csv('mrc_luang_data.csv')

ds_mrc['Timestamp'] = pd.to_datetime(ds_mrc['Timestamp'].str[:10], errors='coerce')
ds_mrc = ds_mrc.groupby("Timestamp", as_index = False)['Value'].mean()
exact_dates3 = list(ds_mrc['Timestamp'])
inflow_data3 = ds_mrc['Value']

## CHOOSE INFLOW DATA 1 or 2 or 3
inflow_data=inflow_data3
exact_dates=exact_dates3

# select dates
date_start=str(exact_dates[0])
year_start=int(date_start[:4])
date_end=str(exact_dates[-1])
year_end=int(date_end[:4])
'''
# convert inflow from m^3/s to m^3/day to apply for a day timestep
for flow in range(len(inflow_data)):
    inflow_data[flow]=inflow_data[flow]*60*60*24
'''    
# plot inflow plot
days=np.linspace(year_start,year_end,len(inflow_data))
plt.plot(days,inflow_data)
plt.title('Inflow Data over Time')
plt.xlabel('Time (years)')
plt.ylabel('Inflow (m^3/day)')

# model dam
min_level=278 # meters
max_level=298 # meters
storage= 1618681000 # m^3
turb_capacity = 7702.8 # m^3/s
area_reservoir = storage/max_level
max_storage = storage
min_storage=area_reservoir*min_level
seconds_in_day = 60*60*24
seconds_in_hour = 60*60
max_power = 1289 #MW
design_head = 18.9 #m
tailwater_level = min_level - design_head

#sediment parameters, mostly placeholders until we can properly parameterize
sed_load = 70*10**6 # T/year
bulk_density = 1.3 #t/m^3
sluice_reduction = 0.3 #30% reduction
flush_fraction = .3 
dredge_volume = 5 * 10 **6

# monetary parameters
electricty_price = 50 #$/MW
sluice_cost = 2*10**6 #$/Year
flush_cost = 1 #$/m^3
dredge_cost = 1 #$/m^3

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

def sluicing(TE, sediment_vol):
    # let sediment flow through during high flows
    TE = TE*(1 - sluice_reduction)
    dv = TE*sed_load/bulk_density
    cost = sluice_cost
    return sediment_vol + dv, cost

def flushing(TE, sediment_vol):
    # reduce deposited amount by a set fraction
    dv = TE*sed_load/bulk_density
    flushed = dv*flush_fraction
    cost = flushed*flush_cost
    return sediment_vol + dv - flushed, cost

def dredging(TE, sediment_vol):
    # a fixed volume is dredged out each year
    dv = TE*sed_load/bulk_density
    sediment_vol = sediment_vol + dv
    removed = dredge_volume
    if removed > sediment_vol:   # can't dredge more than existing amount of seds
        removed = sediment_vol
    cost = removed*dredge_cost
    return sediment_vol - removed, cost




def run_dam(ts, flow_data, sed_strat):
    #ts is time_step so we can experiment with appropriate timesteps given dam fills very quickly
    ts_sec = ts * seconds_in_hour # seconds in timestep
    steps_day = int(24/ts) #steps in a day
    steps_year = 365 * steps_day
    steps = len(flow_data)* steps_day
    
    max_storage = storage
    min_storage = area_reservoir *min_level
    sediment_vol = 0
    
    ##initialize lists
    # Although there was not a reservoir in 1984 we will 
    # imagine that the reservoir starts full
    s_lis = [min_storage] #m^3
    energy_lis = [0] #MW-hour
    tot_discharge_lis=[0] #m^3
    turbine_water_lis=[0] #m^3
    turbine_time_lis=[0] #hour
    spillway_lis=[0] #m^3
    capacity_lis=[]
    cost_lis = []

    for j in range(steps - 1):
        day = (j+1)//steps_day
        #tackle sediment once per year
        if j % steps_year ==0:
            annual_inflow = sum(flow_data[day:day+365])*24*seconds_in_hour
            te = TE(max_storage, annual_inflow)
            sediment_vol, cost = sed_strat(te, sediment_vol)
            #decreasing space based on amount of sediment
            max_storage = storage - sediment_vol
            min_storage = max_storage*min_level/max_level
            capacity_lis.append(max_storage/(10**6))
            cost_lis.append(cost)
        level = s_lis[j]*max_level/max_storage
        head = level - tailwater_level
        
        # add inflow to storage from previous day
        imagined_storage=flow_data[day]*ts_sec+s_lis[j]
        
        if imagined_storage>min_storage:
            #can release water through turbines to get power
            poss_turb_vol = imagined_storage-min_storage #possible volume through turbines
            turb_sec = poss_turb_vol/turb_capacity #possible run time of turbines
            if turb_sec>=ts_sec:
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
                energy=max_power*turb_time/seconds_in_hour*head/design_head
            else: # turbine runs less than full day and no need to lose water through spillways
                spill=0
                spillway_lis.append(spill)
                turb_time=turb_sec # as calculated above
                turbine_time_lis.append(turb_time/seconds_in_hour)
                turb_water=poss_turb_vol
                turbine_water_lis.append(turb_water)
                # calculate energy
                energy=max_power*turb_sec/seconds_in_hour*head/design_head
            energy_lis.append(energy)
            tot_discharge=spill+turb_water
            tot_discharge_lis.append(tot_discharge)
        if imagined_storage<=min_storage:
            energy_lis.append(0)
            tot_discharge=0
            tot_discharge_lis.append(tot_discharge)
            turbine_water_lis.append(0)
            turbine_time_lis.append(0)
            spillway_lis.append(0) 
        
        new_storage = imagined_storage-tot_discharge
        if new_storage>max_storage:
            print('Something is wrong! New storage cannot exceed maximum storage')
        s_lis.append(new_storage)
        
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
    #can be changed later when we get to optimization if there's a better form that works for us
    results = {'storage': s_lis,
               'energy': energy_lis,
               'discharge': tot_discharge_lis,
               'turbine_water': turbine_water_lis,
               'turbine_time': turbine_time_lis,
               'spillway': spillway_lis,
               'capacity': capacity_lis,
               'annual_energy': annual_energy_lis,
               'cost': cost_lis,
               'revenue': revenue_lis,
               'profit': profit_lis}
    return results

time_step = 8
results = run_dam(time_step, inflow_data, dredging)
years = np.arange(len(results['capacity'])) + year_start
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
ax1.plot(years, results['capacity'])
ax2.plot(years, np.array(results['annual_energy'])/1000)  # GWh
ax3.plot(years, np.array(results['profit'])/1e6)          # million $
ax1.set_ylabel('Capacity (Mm$^3$)')
ax1.set_title('Reservoir Capacity')
ax1.legend()
ax2.set_ylabel('Energy (GWh/yr)')
ax2.set_title('Annual Energy Production')
ax3.set_ylabel('Profit (million $/yr)')
ax3.set_title('Annual Profit (energy revenue - sediment cost)')
ax3.set_xlabel('Year')
plt.tight_layout()


##From older version of the model without sediment
'''   
# plot model data, zoom in to random range
plt.figure()
plt.plot(days[2000:3000], tot_discharge_lis[2000:3000])
plt.xlabel('Time (years)')
plt.ylabel("Water Discharge (m^3/day)")
plt.title("Total Discharge (m^3)")
plt.figure()
plt.plot(days[2000:3000], spillway_lis[2000:3000])
plt.xlabel('Time (years)')
plt.ylabel('Water Discharge (m^3/day)')
plt.title('Discharge Through Spillway')
plt.figure()
plt.plot(days[2000:3000], turbine_water_lis[2000:3000])
plt.xlabel('Time (years)')
plt.ylabel('Water (m^3/day)')
plt.title('Water Through Turbines')
plt.figure()
plt.plot(days[2000:3000], energy_lis[2000:3000])
plt.xlabel('Time (years)')
plt.ylabel('Energy (MWh/day)')
plt.title('Energy Production')
plt.figure()
plt.plot(days[2000:3000], turbine_time_lis[2000:3000])
plt.xlabel('Time (years)')
plt.ylabel('Time Turbines are Active (hours/day)')
plt.title('Turbine Time')
'''
'''
#comparing different data sources
grdr = pd.Series(inflow_data1.values, index=pd.to_datetime(exact_dates1), name='GRDR')
reach = pd.Series(inflow_data3.values, index=pd.to_datetime(exact_dates3), name='Reach Hydro')

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
ax1.plot(grdr.index, grdr, label='GRDR', alpha=0.8, lw=0.8)
ax1.plot(reach.index, reach, label='Reach Hydro', alpha=0.8, lw=0.8)
ax1.set_ylabel('Inflow (m$^3$/s)')
ax1.set_title('Xayaburi Inflow: GRDR vs Reach Hydro')
ax1.legend()
both = pd.concat([grdr, reach], axis=1, join='inner').dropna()
diff = both['Reach Hydro'] - both['GRDR']
ax2.plot(diff.index, diff, color='gray', lw=0.8)
ax2.axhline(0, color='k', lw=0.5)
ax2.set_ylabel('Reach − GRDR (m$^3$/s)')
ax2.set_xlabel('Date')
plt.tight_layout()
'''


# model each sediment strategy
# Thoughts on sediment modelling
# need to model the sediment input based on constant value
# need to model the sediment output based on what sediment strategy we use

