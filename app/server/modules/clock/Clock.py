from code import interact
from datetime import datetime, timedelta, time, date
from pickletools import floatnl
from random import randint
import random
import numpy as np
from scipy.stats import norm

class Clock():
    """
    A class used to determine in-game time and compute values related to it
    """

    @staticmethod
    def get_current_gametime(start_time: datetime, seed_date: str, time_multiplier: int = 10000) -> datetime:
        """
        Returns the current gametime as a datetime value based on a scaled multiple of real-world time

        Parameters
        ----------
        start_time : datetime
            The real-world datetime value when the game started running
        seed_date : str
            The time in-game when the simulation should start (example: 2022-01-01 will be the earliest in-game time)
        time_multiplier : int
            The value representing the multiplier between real-world and in-game time (default is 10000)

        Returns
        ----------
        datetime
            A datetime value representing the current in-game time
        """
        # TODO: time_multiplier should be read from global config
        seed_date = datetime.timestamp(Clock.from_string(
            seed_date, format="%Y-%m-%d"))  # TODO this could be simpler
        start_time = Clock.from_string(start_time).timestamp()
        computed_datetime = seed_date + \
            (Clock._get_elapsed_time(start_time) * time_multiplier)

        return computed_datetime
    
    @staticmethod
    def generate_bimodal_timestamp(start_date: date, start_hour, day_length):
        """
        Generate a timestamp value based on a bimodal distribution
        centered around the middle of the time range specified.

        Parameters:
            start_time_str (str): A string representing the start time.
            end_time_str (str): A string representing the end time.

        Returns:
            A datetime object representing the generated timestamp.
        """
        start_time = datetime.combine(start_date, time(hour=start_hour))
        end_time = start_time + timedelta(hours=day_length)
        midpoint = start_time + (end_time - start_time) / 2
        bimodal_mean = [midpoint - timedelta(hours=2), midpoint + timedelta(hours=2)]
        bimodal_std = [timedelta(hours=1), timedelta(hours=1)]
        weights = [0.4, 0.6]
        # Generate a random index based on the weights
        index = np.random.choice([0, 1], p=weights)
        # Generate a random timestamp based on the selected bimodal distribution
        timestamp = datetime.fromtimestamp(norm.rvs(
            loc=bimodal_mean[index].timestamp(),
            scale=bimodal_std[index].total_seconds()))
        
        return timestamp

    @staticmethod
    def get_current_gametime_as_str(start_time: datetime, seed_date: str) -> str:
        """
        Return the current simulated time as timestamp
        """
        gametime = Clock.get_current_gametime(
            start_time=start_time, seed_date=seed_date)
        return str(gametime)

    @staticmethod
    def _get_elapsed_time(start_time: float) -> int:
        """
        Get number of real seconds since game was started
        """
        return datetime.now().timestamp() - start_time

    @staticmethod
    def is_business_hours(timestamp: float) -> bool:
        """
        params: time is a datetime object
        Returns true if time is within business hours (M-F 7-6PM local time)
        Returns false otherwise
        """
        time = datetime.fromtimestamp(
            timestamp)  # convert timestamp to datetime

        if time.weekday in ["1", "7"]:
            return False
        elif time.hour > 18 or time.hour < 7:
            return False
        else:
            return True

    @staticmethod
    def from_string(time: str, format: str = "%Y-%m-%d %H:%M:%S.%f") -> datetime:
        """
        params: time - string in datetime format (.e.g '2014-03-22 07:54:43.010126')
        Return datetime object
        """
        return datetime.strptime(time, format)

    @staticmethod
    def from_string_to_timestamp(time: str, format: str = "%Y-%m-%d %H:%M:%S.%f") -> float:
        """
        params: time - string in datetime format (.e.g '2014-03-22 07:54:43.010126')
        Return timestamp float
        """
        return datetime.strptime(time, format).timestamp()

    @staticmethod
    def from_timestamp_to_string(timestamp: float) -> str:
        """
        params: timestamp - datetime as a timestamp (float)
        Return timestamp as string
        """
        return str(datetime.fromtimestamp(timestamp))

    @staticmethod
    def increment_time(start_time: float, increment: int) -> float:
        """
        Increment time locally without impacting system time
        params: start_time - datetime object
        params: increment - number of seconds to add to time
        Returns new local datetime
        """
        return start_time + increment
    
    @staticmethod
    def weekday_to_string(weekday_int: int) -> str:
        return ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][weekday_int]

    @staticmethod
    def delay_time_in_working_hours(start_time: float, factor: str, workday_start_hour: int, workday_length_hours: int, working_days_of_week: list) -> float:
        """
        This function can be called to increment a time within business hours for a given work schedule
        NOTE: This function only works for forward increments. Reverse increments cannot be corrected to working hours
        """
        current_date = date.fromtimestamp(start_time)
        current_workday_start = datetime.combine(current_date, time(hour=workday_start_hour))
        current_workday_end = current_workday_start + timedelta(hours=workday_length_hours)

        # Try to do a regular increment
        incremented_time_not_corrected = Clock.delay_time_by(start_time, factor)

        # Check to see if that time is outside the current workday
        if incremented_time_not_corrected > datetime.timestamp(current_workday_end):
            # If it is, increment the day
            new_date = datetime.fromtimestamp(incremented_time_not_corrected) + timedelta(days=1)
            # Check to make sure the weekday is a working day
            while (Clock.weekday_to_string(new_date.weekday()) not in working_days_of_week):
                # If it's not, increment the day again
                new_date += timedelta(days=1)
            return datetime.timestamp(Clock.generate_bimodal_timestamp(start_date=new_date, start_hour=workday_start_hour, day_length=workday_length_hours))
        else:
            return incremented_time_not_corrected
        


    @staticmethod
    def delay_time_by(start_time: float, factor: str, is_negative=False, is_random=False) -> float:
        """
        Increment time by month, days, hours, minutes, seconds
        """
        if factor not in ["month","days","hours","minutes","seconds"]:
            raise Exception('"factor" must be one of the following values: ["days","hours","minutes","seconds"]')
        
        days, hours, minutes, seconds = 0, 0, 0, 0

        if is_random:
            direction = random.choice([1, -1])
        elif is_negative:
            direction = -1
        else:
            direction = 1

        if factor == "month":
            days = randint(1, 31) * direction
        if factor == "days":
            days = randint(1, 7) * direction
        elif factor == "hours":
            hours = randint(1,24) * direction
        elif factor == "minutes":
            minutes = randint(1, 60) * direction
        elif factor == "seconds":
            seconds = randint(1, 60) * direction



        increment_value = (days * 86400) + (hours * 3600) + (minutes * 60) + seconds

        return start_time + increment_value
