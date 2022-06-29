from flask import Flask
import pika
from flask import request
import uuid
import threading
import time
import pickle
import json
import time
import datetime
import requests
import os
import json
import time
import os
import shutil
import sys
from subprocess import check_output
from xxlimited import Null
from dateutil.parser import *
import paramiko
from collections import OrderedDict

# Function to preform aws cli commands
def aws_cli(command):
    output = check_output(
        command,
        shell=True
    )
    if output != b'':
        try:
            output = json.loads(output)
        except ValueError as e:
            output = output.decode('ascii').strip()
        return output

# Instance worker configuration, here we unzip the files and create the docker image
def config_inst(key_name, host_name, inst):
    
    fname = 'src2'

    # Inner folder of upload (to run later)
    inner = os.listdir(fname)[0]
    
    # Zip upload folder
    zip_path = shutil.make_archive(fname, 'zip', fname)
    zip_fname = fname + '.zip'
    
    # Wait until status checks complete
    while True:
        output = aws_cli('aws ec2 describe-instance-status --instance-id {}'.format(inst))
        if len(output['InstanceStatuses']):
            if output['InstanceStatuses'][0]['InstanceStatus']['Status'] == 'initializing':
                print('initializing, waiting 10 seconds...')
                time.sleep(10)
            else:
                print(output)
                break
        else:
            print('waiting 10 seconds...')
            time.sleep(10)

    # Get public DNS
    output = aws_cli('aws ec2 describe-instances --instance-id {}'.format(inst))
    print(output)
    dns = output['Reservations'][0]['Instances'][0]['PublicDnsName']

    # Initialize SSHClient w/paramiko
    k = paramiko.RSAKey.from_private_key_file(
        "{}.pem".format(key_name)
    )
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # SSHClient 
    c.connect(hostname=dns, username="ec2-user", pkey=k)

    # Upload docker image
    cmd = 'sudo yum update'
    stdin, stdout, stderr = c.exec_command('sudo yum update')
    stdin, stdout, stderr = c.exec_command('sudo amazon-linux-extras install docker')
    stdin, stdout, stderr = c.exec_command('sudo service docker start')

    sftp = c.open_sftp()

    # Upload zip file
    upload = sftp.put(
        zip_path,
        '/home/ec2-user/' + zip_fname
    )
    def exec_shutdown_write(c, command, t=1000):
        stdin, stdout, stderr = c.exec_command(command, timeout=t)
        stdout.channel.shutdown_write()
        return sys.stdout.write(str(stdout.read()))

    # Unzip
    exec_shutdown_write(c, 'unzip -o ' + fname)

    # Check if upload complete
    exec_shutdown_write(c, 'ls')

    # Build docker image
    x = exec_shutdown_write(c,'sudo usermod -a -G docker ec2-user')
    x = exec_shutdown_write(c,'sudo chmod 666 /var/run/docker.sock')
    exec_shutdown_write(c, 'sudo amazon-linux-extras install docker')
    x = exec_shutdown_write(c, 'sudo amazon-linux-extras install docker')
    x = exec_shutdown_write(c, 'sudo service docker start')
    x = exec_shutdown_write(c,'sudo curl -L "https://github.com/docker/compose/releases/download/v2.6.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose')
    x = exec_shutdown_write(c,"sudo chmod +x /usr/local/bin/docker-compose")
    x = exec_shutdown_write(c,'sudo service docker start')
    x = exec_shutdown_write(c,'sudo usermod -a -G docker ec2-user')
    x = exec_shutdown_write(c,'sudo chmod 666 /var/run/docker.sock')
    
    # after unzip 
    exec_shutdown_write(c, 'printf "RABBIT={}" > .env'.format(host_name))
    x = exec_shutdown_write(c, 'docker-compose --env-file .env up -d')
    x = exec_shutdown_write(c, 'docker ps -a') 

    c.close() 

# This is deploy function which deploys the aws instace worker
# default we deploy one worker
# if intsnace_id is different than 0, we need to delete it, because it is to slow and has timeout.
def deploy(key, s_key, region, vpc, host_name, num_workers=1, instance_id=0):
    
    image = 'ami-0947d2ba12ee1ff75' # Free tier Amazon Linux 2 AMI
    region = aws_cli('rm -rf /root/.aws/')

    aws_cli('aws configure set aws_access_key_id {}; aws configure set aws_secret_access_key {};aws configure set region {};'.format(key, s_key, region))
   
    # Set key 
    key_name = str(int(time.time()))

    # deleting instance with timeout
    if instance_id != 0:
        aws_cli('delete-instance --instance-id {}'.format(instance_id))

    # Get subnet for default VPC
    output = aws_cli('aws ec2 describe-subnets --filter "Name=vpc-id,Values={}"'.format(vpc))
    print(output)
    subnet = output['Subnets'][0]['SubnetId']

    # Make new security group
    # Note: needs to belong to proper network (same as subnet)
    output = aws_cli("aws ec2 create-security-group --vpc-id {} --group-name {} --description {}".format(vpc, key_name, key_name))
    print(output)
    sg = output['GroupId']

    # Edit inbound rules
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 22 --cidr 0.0.0.0/0'.format(sg))
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 4369 --cidr 0.0.0.0/0'.format(sg))
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 15672 --cidr 0.0.0.0/0'.format(sg))
    output = aws_cli('aws ec2 authorize-security-group-ingress --group-id {} --protocol tcp --port 5672 --cidr 0.0.0.0/0'.format(sg))

    # Create key
    output = aws_cli("aws ec2 create-key-pair --key-name {} --output text > {}.pem".format(key_name, key_name))

    # The key is generating with fingerprint up front, which confuses paramiko (later in script)
    key_str = open('{}.pem'.format(key_name), 'r').read()

    # Have to remove the fingerprint up front for some reason
    with open('{}.pem'.format(key_name), 'w') as w:
        w.write(key_str[key_str.index('-----'):])
    key_str = open('{}.pem'.format(key_name), 'r').read()
    print(key_str)

    # Runs EC2
    output = aws_cli("aws ec2 run-instances --image-id {} --count {} --instance-type t2.micro --key-name {} --security-group-ids {} --subnet-id {}".format(image, num_workers, key_name, sg, subnet))
    print(output)
    for i in range(len(output['Instances'])):
        inst = output['Instances'][i]['InstanceId']
        threading.Thread(target=config_inst, args=((key_name, host_name, inst))).start()
        time.sleep(20)

    
app = Flask(__name__)

# this is the queue in memory for return the results
queue = OrderedDict()
treatment_queue = OrderedDict()
list_files = {}
TIMEOUT="timeout"

class msg(object):
    def __init__(self, corr_id, body):
        self.response = None
        self.corr_id = corr_id
        self.body = body
        queue[self.corr_id] = None

    def enqueue_msg(self, rpc_client):
        if rpc_client.connection.is_closed:
            rpc_client.connect()
        queue[self.corr_id] = None
        # Creating limited time for task to be preformed
        timestamp = time.time()
        self.body['created'] = str(timestamp)
        self.body['expire'] = str(datetime.timedelta(minutes=5).total_seconds())
        body=json.dumps(self.body)
        self.channel.basic_publish(
            exchange='',
            routing_key='rpc_queue',
            properties=pika.BasicProperties(
                reply_to=rpc_client.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=body)
        # answer will be inserted to queue in on_response function in rpc client
        while queue[self.corr_id] is None:
            rpc_client.connection.process_data_events()
        # delete element form queue if timeout
        if self.corr_id in  queue.keys():
            if queue[self.corr_id] == TIMEOUT:
                del queue[self.corr_id]
            # delete info from backup queue because job has already done
            else:
                del treatment_queue[self.corr_id]
            

class RpcClient(object):

    internal_lock = threading.Lock()

    def __init__(self):
        sleepTime = 20
        print(' [*] Sleeping for ', sleepTime, ' seconds.', flush=True)
        time.sleep(sleepTime)
        self.connection = None
        self.channel = None
        self._is_closed = False
        self.open = False
        # get the instance host in order to send the worker rabbit-mq address
        self.host = requests.get('http://169.254.169.254/latest/meta-data/public-hostname').text
        self.connect()
    
    def connect(self):
        self.open = False
        print("Connecting...")
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq',heartbeat=0))
        self.connect_channel()

    def connect_channel(self):
        self.channel = self.connection.channel()

        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True)
        
        print("in connect", flush=True)
        self.open = True
        # Deploying two workers 
        self.deploy_workers(2)


    def deploy_workers(self, num_workers=1):
        threading.Thread(target=deploy, args=(os.environ['ACCESSKEY'], os.environ['ACCESSSECRETKEY'], os.environ['REGION'], os.environ['VPC'], self.host, num_workers)).start()

    # This function is called when a worker finishes its job - on_message_callback
    def on_response(self, ch, method, props, body):
        if 'instance-id' in props.headers.keys():
            # in order to stop while loop in enqueue_msg line 211
            queue[props.correlation_id] = TIMEOUT
            # do auto scaling - call deploy worker & remove worker by id
            deploy(os.environ['ACCESSKEY'], os.environ['ACCESSSECRETKEY'], os.environ['REGION'], self.host, 1, props.headers.instance-id)
            # create new msg object with the info from the backup queue
            msg(props.correlation_id, treatment_queue[props.correlation_id])
            msg.enqueue_msg(self)
        else:
            # update information in queue
            queue[props.correlation_id] = body


rpc = RpcClient()
# other_instance is for the case where use asks for pull completed with large number 
# so we http to the second EC2 to merge results from its queue
other_instance = os.environ['OTHERDNS']

@app.route('/')
def index():
    return 'OK'

@app.route('/enqueue', methods=['PUT'])
def enqueue():
    args = request.args
    iterations = args.get('iterations')
    if iterations is None:
        return "you must specify iterations"
    corr_id = str(uuid.uuid4())
    data = request.get_data() # in binary
    if data is None:
        return "you must add binary file"
    print(data, flush=True)
    body={'corr_id': corr_id, 'payload': data.decode('utf-8'), 'iterations': str(iterations)}
    print(body, flush=True)
    # Save info in treatment queue in case of timeout 
    treatment_queue[corr_id] = body
    msg(corr_id, body)
    threading.Thread(target=msg.enqueue_msg, args=(rpc)).start()
    return "sent to proccesing, the id is " + corr_id


@app.route("/results")
def send_results():
    print(str(queue.items()))
    return str(queue.items())

@app.route("/stop_wokrer", methods=['POST'])
def stop_worker(args):
    worker_id = args.get('instnace_id')
    print("stopping worker")
    aws_cli('delete-instance --instance-id {}'.format(worker_id))

@app.route("/pullCompleted", methods=['POST'])
def pull():
    args = request.args
    num = args.get('top')
    if num is None:
        return "you must specify num of completed values"
    return_list = []
    for i in range(int(num)):
        if len(queue) > 0:
            return_list.append((queue.popitem(last=False)))
        else:
            # we want to join the other queue from the other ec2 instnace 
            if(i > 0):
                other_list_bytes = requests.post(f"http://{other_instance}/pullCompleted?top={int(num)- i}").content
                other_list_str = other_list_bytes.decode("utf-8") 
                other_list = other_list_str.strip('][').split(', ')
                return_list += other_list
    return str(return_list)

if __name__ == '__main__':
    app.run(host='0.0.0.0')


