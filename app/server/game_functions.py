import glob
from flask_security import roles_required

from flask import Blueprint, request, render_template, \
                  flash, g, session, redirect, url_for, abort, current_app, jsonify
from sqlalchemy import asc
from  sqlalchemy.sql.expression import func, select

# Import module models (i.e. Company, Employee, Actor, DNSRecord)
from app.server.models import db, GameSession
from app.server.modules.organization.Company import Company, Employee
from app.server.modules.infrastructure.DNSRecord import DNSRecord
from app.server.modules.logging.uploadLogs import LogUploader
from app.server.modules.email.email_controller import gen_email
from app.server.modules.outbound_browsing.browsing_controller import *
from app.server.modules.infrastructure.passiveDNS_controller import *
from app.server.modules.organization.company_controller import create_company
from app.server.modules.outbound_browsing.browsing_controller import browse_random_website
from app.server.modules.inbound_browsing.inbound_browsing_controller import gen_inbound_browsing_activity
from app.server.modules.authentication.auth_controller import auth_random_user_to_mail_server, actor_password_spray
from app.server.modules.helpers.config_helper import read_config_from_yaml
from app.server.modules.endpoints.endpoint_controller import gen_system_files_on_host, gen_user_files_on_host, gen_system_processes_on_host
from app.server.modules.file.malware import Malware
from app.server.modules.helpers.config_helper import load_malware_obj_from_yaml_by_file

from app.server.utils import *
from app.server.modules.file.vt_seed_files import FILES_MALICIOUS_VT_SEED_HASHES
from app.server.utils import AttackTypes

def start_game() -> None:
    """
    This function call starts the game

    1. Get the game session
    2. Generate starter data
    3. Run infinite loop to generate additional activity
    """
    print("Starting the game...")

    # instantiate a logUploader. This instance is used by all other modules to send logs to azure
    # we use a singular instances in order to queue up muliple rows of logs and send them all at once
    global LOG_UPLOADER
    LOG_UPLOADER = LogUploader(queue_limit=10000)
    LOG_UPLOADER.create_tables(reset=True)

    global MALWARE_OBJECTS
    MALWARE_OBJECTS = create_malware()

    # The is current game session
    # This data object tracks whether or not the game is currently running
    # It allows us to start/stop/restart the game from the views
    current_session = db.session.query(GameSession).get(1)
    current_session.state = True

    # get the time manually
    # we are caching this value
    global GAME_START_TIME
    GAME_START_TIME = current_session.start_time

    global GAME_SEED_DATE
    GAME_SEED_DATE = current_session.seed_date
    
    print(f"Game started at {current_session.start_time}")
    # TODO: allow users ot modify start time in the web UI    
    # run startup functions 
    employees = Employee.query.all()
    actors = Actor.query.all()
    if not (employees or actors):
        employees, actors  = init_setup()
    
    print("initialization complete...")
    # This is where the action is
    # While this infinite loop runs, the game continues to generate data
    # To implement games of finite size -> bound this loop (e.g. use a for loop instead)
    # while current_session.state == True:
    count_cycles = 10
    for i in range(count_cycles):
        # generate the activity
        print("##########################################")
        print(f"## Running cycle {i+1} of the game...")
        print("##########################################")
        for actor in actors: 
            if actor.is_default_actor:
                # Default actor is used to create noise
                generate_activity(actor, employees) 
            else:
                # generate activity of actors defined in actor config
                # num_email is actually number of emails waves sent
                # waves contain multiple emails
                # TODO: abstract this out to the actor / make this more elegant
                generate_activity(actor, 
                                  employees, 
                                  num_passive_dns=random.randint(5, 10), 
                                  num_email=random.randint(0, 3), 
                                ) 



    ##########################################
    # deg statements to help time tracking
    # on average, one cycle=one day in game
    game_start_time = get_time()
    game_end_time =  get_time()
    days_elapse_in_game = (game_end_time - game_start_time) /(60*60*24)
    print(f"Game started at {Clock.from_timestamp_to_string(game_start_time)}")
    print(f"Game ended at {Clock.from_timestamp_to_string(game_end_time)}")
    print(f"{days_elapse_in_game} days elapsed in the game")
    print(f"Ran {count_cycles} cycles...")
    ##########################################


def init_setup():
    """
    These actions are conducted at the start of a new game session

    Create company
    Create default actor
    Create Malicious Actors
    Create first batch of legit passive DNS
    Create first batch of malicious passive DNS
    """
    employees = Employee.query.all()
    actors = Actor.query.all()

    # only create employees for the company or actors 
    # if they do not already exist
    if not employees:
        create_company()
        print("making employees")
        employees = Employee.query.all()
        print(f"made {len(employees)} employees")
    if not actors:
        create_actors()
        actors = Actor.query.all()

    # generate some initial activity for the actors
    for actor in actors:
        generate_activity(
                            actor, 
                            employees, 
                            num_passive_dns=actor.count_init_passive_dns, 
                            num_email=actor.count_init_email
                        ) 

        if AttackTypes.RECONNAISSANCE_VIA_BROWSING.value in actor.get_attacks():
            gen_inbound_browsing_activity(actor, 30) #TODO: Fix this to read from config

    
    # all_dns_records = DNSRecord.query.all()
    # shuffle the dns records so that pivot points are not all next to each other in azure
    # random.shuffle(all_dns_records)
    # all_dns_records = [d.stringify() for d in all_dns_records]
    # upload_dns_records_to_azure(all_dns_records)

    # for actor in actors:
    #     print(f"{actor.name}: {actor.get_attacks_by_type('email')}")

    return employees, actors

    
def generate_activity(actor: Actor, employees: list, 
                        num_passive_dns:int=300, num_email:int=1000, 
                        num_random_browsing:int=500, 
                        num_auth_events:int=400,
                        count_of_user_endpoint_events=5,
                        count_of_system_endpoint_events=100) -> None:
    """
    Given an actor, generates one cycle of activity for users in the orgs 
    based on the attack types that they have defined

    The Default actor is used to represent normal company activities
    """
    print(f" activity for actor {actor.name}")
    # Generate passive DNS for specified actor
    gen_passive_dns(actor, num_passive_dns)

    # Generate emails for random employees for specified actor
    # only if either the actor is supposed to send email 
    # OR they are the default actor (generate email noise)
    # TODO: handle number of emails generated in the function
    if AttackTypes.PHISHING_VIA_EMAIL.value in actor.get_attacks()\
        or AttackTypes.MALWARE_VIA_EMAIL.value in actor.get_attacks()\
        or actor.is_default_actor:
        gen_email(employees, get_company().get_partners(), actor, num_email)

    # Perform password spray attack
    if AttackTypes.PASSWORD_SPRAY.value in actor.get_attacks():
        actor_password_spray(
            actor=actor, 
            num_employees=random.randint(5,50),
            num_passwords=5
        )

    # generate watering hole activity
    if AttackTypes.MALWARE_VIA_WATERING_HOLE.value in actor.get_attacks():
        actor_stages_watering_hole(
            actor=actor,
            num_employees=random.randint(5, 10),
            link_type="malware_delivery"
        )

    #TODO Implement cred phishing via watering holde
    if AttackTypes.PHISHING_VIA_WATERING_HOLE.value in actor.get_attacks():
        actor_stages_watering_hole(
            actor=actor,
            num_employees=random.randint(5, 10),
            link_type="credential_phishing"
        )

    # Generate browsing activity for random emplyoees for the default actor
    # browsing for other actors should only come through email clicks
    if actor.is_default_actor:
        browse_random_website(employees, actor, num_random_browsing)
        auth_random_user_to_mail_server(employees, num_auth_events)
        gen_inbound_browsing_activity(actor, num_random_browsing)
        gen_system_files_on_host(count_of_system_endpoint_events)
        gen_user_files_on_host(count_of_user_endpoint_events)
        gen_system_processes_on_host(count_of_system_endpoint_events)

def create_actors() -> None:
    """
    Create a malicious actor in the game and adds them to the database
    Actors are read in from yaml files in the actor_configs folder

    TODO: there should be some validation of actor configs prior to creation
    """

    # instantial a default actor - this actor should always exist
    # the default actor is used to generate background noise in the game
    default_actor = Actor(
        name = "Default",  # Dont change the name!
        effectiveness = 99,
        count_init_passive_dns=500, 
        count_init_email= 5000, 
        count_init_browsing=5000,
        domain_themes = wordGenerator.get_words(1000),
        sender_themes = wordGenerator.get_words(1000)
    )

    # load add default_actor
    actors = [default_actor]

    # use yaml configs to load other actors
    # read yaml file for each new actor, load json from yaml
    actor_configs = glob.glob("app/game_configs/actors/*.yaml") 
    for file in actor_configs:
        actor_config = read_config_from_yaml(file)
        # use dictionary value to instantiate actor
        if actor_config:
            # print(f"adding actor: {actor_config}")
            # use dict to instantiate the actor
            actors.append(
                Actor(**actor_config)
            )


    # add all the actors to the database
    try:
        for actor in actors:
            db.session.add(actor)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print("Failed to create actor %s" % e)
        
def create_malware() -> "list[Malware]":
    """
    Load all malware configs from YAML and configure a list of Malware objects
    """
    malware_objects = []
    malware_configs = glob.glob(f"app/game_configs/malware/*.yaml")
    for path in malware_configs:
        malware_objects.append(load_malware_obj_from_yaml_by_file(path))
    
    malware_objects = assign_hash_to_malware(malware_objects)
    return malware_objects

def assign_hash_to_malware(malware_objects: "list[Malware]") -> "list[Malware]":
    """
    Take all available VT hashes and assign them to malware families 
    there should be a 1-1 mapping of hash to malware family
    """
    # Look through available hashes and assign them to malware families via a round robin
    while FILES_MALICIOUS_VT_SEED_HASHES:
        for malware_object in malware_objects:
            if not FILES_MALICIOUS_VT_SEED_HASHES:
                break
            # take a hash and remove it from our list of hashes
            hash = FILES_MALICIOUS_VT_SEED_HASHES.pop()
            malware_object.hashes.append(hash) # TODO: This might not work!!
   
    return malware_objects

