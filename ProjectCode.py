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

## IMPORTED DATA FROM https://zenodo.org/records/13951712 (What Prof. Galleli gave us)
nc_path = "GRDR_v1.0.0_region_4.nc"
ds = xr.open_dataset(nc_path, chunks={'time': 'auto'})
# reach ID for the region above Xayaburi Dam
target_reach = 44021314
# access data
ds = ds['discharge'].sel(reach=target_reach).to_dataframe().reset_index()
exact_dates1 = list(ds['time'])
inflow_data1 = ds['discharge']


## IMPORTED DATA FROM https://maps.reachhydro.org/?project=global (has different values for some reason)
ds = pd.read_csv('flow_series.csv')
exact_dates2 = list(ds['Date'])
inflow_data2 = ds['Flow']

## CHOOSE INFLOW DATA 1 or 2
inflow_data=inflow_data1
exact_dates=exact_dates1

# select dates
date_start=str(exact_dates[0])
year_start=int(date_start[:4])
date_end=str(exact_dates[-1])
year_end=int(date_end[:4])

# convert inflow from m^3/s to m^3/day to apply for a day timestep
for flow in range(len(inflow_data)):
    inflow_data[flow]=inflow_data[flow]*60*60*24
    
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

##initialize lists
# Although there was not a reservoir in 1984 we will 
# imagine that the reservoir starts full
s_lis = [min_storage] #m^3
energy_lis = [0] #MW-hour
tot_discharge_lis=[0] #m^3
turbine_water_lis=[0] #m^3
turbine_time_lis=[0] #hour
spillway_lis=[0] #m^3


for j in range(len(inflow_data)-1):
    # add inflow to storage from previous day
    imagined_storage=inflow_data[j+1]+s_lis[j] 
    if imagined_storage>min_storage:
        #can release water through turbines to get power
        poss_turb_vol = imagined_storage-min_storage #possible volume through turbines
        turb_sec = poss_turb_vol/turb_capacity #possible run time of turbines
        if turb_sec>=seconds_in_day:
            #turbine runs the whole day, any remaining water must be lost through spillways
            turb_time=seconds_in_day
            turbine_time_lis.append(turb_time/seconds_in_hour)
            turb_water=turb_time*turb_capacity
            turbine_water_lis.append(turb_water)
            remaining_water=imagined_storage-turb_water
            if remaining_water>max_storage: #must release water through spillway
                spill=remaining_water-max_storage
            else: #water level is below maximum line after turbines run, no need for spill
                spill=0
            spillway_lis.append(spill)
            #calculate energy
            energy=max_power*turb_time/seconds_in_hour
        else: # turbine runs less than full day and no need to lose water through spillways
            spill=0
            spillway_lis.append(spill)
            turb_time=turb_sec # as calculated above
            turbine_time_lis.append(turb_time/seconds_in_hour)
            turb_water=poss_turb_vol
            turbine_water_lis.append(turb_water)
            # calculate energy
            energy=max_power*turb_sec/seconds_in_hour
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

# model each sediment strategy
# Thoughts on sediment modelling
# need to model the sediment input based on constant value
# need to model the sediment output based on what sediment strategy we use

