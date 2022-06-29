from wsgiref import headers
import pika
import time
import json 
import datetime
import os
import requests
import threading

sleepTime = 20
print(' [*] Sleeping for ', sleepTime, ' seconds.')
time.sleep(sleepTime)

print(' [*] Connecting to server ...')
address=os.environ['RABBIT']
connection = pika.BlockingConnection(pika.ConnectionParameters(host=address))
channel = connection.channel()
channel.queue_declare(queue='rpc_queue')

print(' [*] Waiting for messages.')

TIMEOUT="timeout"
start = time.time()
instnace_id = requests.get("http://169.254.169.254/latest/meta-data/instance-id")

# declaring expire time for scaling out 
EXPIRE_TIME = datetime.timedelta(minutes=10).total_seconds
# varaible to stop thread timer loop when a new message is coming we want to stop current runnig thread
# and start a new one
stop_thread = False

# this is a timer function for scaling out 
def check_if_free(start_time):
    global stop_thread
    # sleeping to create spaces between threads updating global varaible stop_thread
    time.sleep(20)
    # cretae while loop to calculate free time
    # stops in two caseses - if another stop_thread is True or if time has passed
    while ((time.time() - start_time < EXPIRE_TIME)):
        if stop_thread:
            break
    else:
        if not stop_thread:
            channel.stop_consuming()
            # doing request to adress which is the host to stop the worker
            requests.post(address + ":80/stop_wokrer", params=instnace_id)
        else:
            stop_thread = True

# working function to read info in batches
def work(buffer, iterations, expire): 
    import hashlib
    output = hashlib.sha512(buffer).digest() 
    start = time.time()
    for i in range(int(iterations) - 1):
        print(time.time() - start, flush=True)
        # if there is timeout we stop the process
        if (time.time() - start > expire):
            return TIMEOUT
        output = hashlib.sha512(output).digest()
    print(output, flush=True)
    return output

# This function is called once a message is taken from the queue
def on_request(ch, method, props, body):
    
    # starting a new thread  
    # updating global start_thread varaible 
    # in order to stop while loop of the prev thread
    global stop_thread
    stop_thread = True
    start_working = time.time()
    threading.Thread(target=check_if_free, args=(start_working)).start()

    timestamp = time.time()
    now = datetime.datetime.now()

    data = json.loads(body.decode("utf-8"))
    expire = float(data['expire'])
    output = work(data['payload'].encode("utf-8"), data['iterations'].encode("utf-8"), expire)
    
    created = float(data['created'][0])
    time_taken = timestamp - created
    headers= {'time':str(time_taken)}

    # if timeout we want to get the instance id and send it for scaling
    if output == TIMEOUT:
        instnace_id = requests.get("http://169.254.169.254/latest/meta-data/instance-id")
        headers= {'instnace_id':instnace_id}
        output = b'TIMEOUT'
        
    ch.basic_publish(exchange='',
                     routing_key=props.reply_to,
                     properties=pika.BasicProperties(
                     correlation_id=props.correlation_id,
                     headers= headers),
                     body=output)
    ch.basic_ack(delivery_tag=method.delivery_tag)


channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='rpc_queue', on_message_callback=on_request)

print(" [x] Awaiting RPC requests")
channel.start_consuming()

start_working = time.time()
threading.Thread(target=check_if_free, args=(start_working)).start()

