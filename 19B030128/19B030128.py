# pylint: disable=no-member
import pygame
import pika
from enum import Enum
import sys
import uuid
import json
from threading import Thread
import math
from os import path
import random
import time

#---------------------------------- M A I N ------------------------------------

pygame.init()
im_dirct = path.join(path.dirname(__file__), 'boom') #for sprites

width = 800
height = 600
screen = pygame.display.set_mode((width, height))

FPS = 40
scores = {}

mode1 = False
mode2 = False
mode3 = False
goinmulti = False
goinai = False

#-----------------------IMAGES-----------------
gm = pygame.image.load("game-over.png")
pl = pygame.image.load('laptop.png')
power = pygame.image.load('superpower.png')
backgroundImage4 = pygame.image.load("bg4.jpg")
pygame.display.set_caption("Tanks War")
iconImage = pygame.image.load("icon.png")
pygame.display.set_icon(iconImage)
taaanks = pygame.image.load('taanks.png')
menu = pygame.image.load('bg.png')
wall = pygame.image.load('wall.png')
roomscreen = pygame.image.load('rooms.png')

#----------------------FONTS---------------------
smallfont = pygame.font.SysFont("skia", 15)
mediumfont = pygame.font.SysFont("impact", 40)
bigfont = pygame.font.SysFont('laomn', 72)
classic = pygame.font.Font('freesansbold.ttf', 15) 

timetick = pygame.time.Clock()
pressed = pygame.key.get_pressed() 

#----------------------SOUNDS-------------------
gamemusic = pygame.mixer.Sound('gamemusic.wav')
shootsound = pygame.mixer.Sound('shoot.wav')
hitsound = pygame.mixer.Sound('hit.wav')
gameover = pygame.mixer.Sound('gameover.wav')
gamemusic.set_volume(0.1)
gamemusic.play(-1)

class Blowing(pygame.sprite.Sprite):
    def __init__(self, center, size):
        pygame.sprite.Sprite.__init__(self)
        self.size = size
        self.image = imboom[self.size][0]
        self.rect = self.image.get_rect()
        self.rect.center = center
        self.dist = 0
        self.radius = 40
        self.remake = pygame.time.get_ticks()

    def update(self):
        nowsec = pygame.time.get_ticks()
        if nowsec - self.remake > self.radius:
            self.remake = nowsec
            self.dist += 1
            if self.dist == len(imboom[self.size]):
                self.kill()
            else:
                center = self.rect.center
                self.image = imboom[self.size][self.dist]
                self.rect = self.image.get_rect()
                self.rect.center = center

imboom = {}
imboom['exp'] = []
imboom['diff'] = []
for i in range(9):
    cur = 'b0{}.png'.format(i)
    curpng = pygame.image.load(path.join(im_dirct, cur)).convert()
    curpng.set_colorkey((0,0,0))
    png_exp = pygame.transform.scale(curpng, (75, 75))
    imboom['exp'].append(png_exp)
    png_diff = pygame.transform.scale(curpng, (32, 32))
    imboom['diff'].append(png_diff)

sprites = pygame.sprite.Group()

#---------------------------RPC CLIENT-------------------
class TankRPC:
    def __init__(self):
        self.connection  = pika.BlockingConnection(pika.ConnectionParameters(host='34.254.177.17',port=5672,virtual_host='dar-tanks',credentials=pika.PlainCredentials(username='dar-tanks',password='5orPLExUYnyVYZg48caMpX')))
        self.channel = self.connection.channel()             
        queue = self.channel.queue_declare(queue='',exclusive=True,auto_delete=True) # exclusive = true - удаляет queue после того как consumer удалиться
        self.callback_queue = queue.method.queue # answer comes in this queue
        self.channel.queue_bind(exchange='X:routing.topic',queue=self.callback_queue)# байндим очередь в обменной точке
        self.channel.basic_consume(queue=self.callback_queue,on_message_callback=self.on_response,auto_ack=True) # auto_ack = True - когда message отпр consumer'y оно автоматом удалится,  data from server comes in on_message_callback 
        self.response = self.corr_id = self.token = self.tank_id = self.room_id = None 

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = json.loads(body) # to parse body - returns a json object
            print(self.response)

    def request(self, key, report={}):     #функция будет отправлять наши запросы на сервер
        self.response = None
        self.corr_id = str(uuid.uuid4()) #we use uuid4() to obtain unique id(uuid = Universally unique identifier)  
        self.channel.basic_publish(
            exchange='X:routing.topic',
            routing_key=key,
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=json.dumps(report) #меняем в json формат
        )
        while self.response is None:
            self.connection.process_data_events()

    def server_test(self): # to check server status
        self.request('tank.request.healthcheck')
        return self.response['status']== '200' # if server active - returns 200, else 400

    
    def registration(self, room_id): #request #2
        global name
        report = {'roomId': room_id} #report or message
        self.request('tank.request.register', report)
        if 'token' in self.response:
            self.token = self.response['token']
            self.tank_id = self.response['tankId']
            name = self.tank_id
            self.room_id = self.response['roomId']
            return True
        return False

    def turn_tank(self, token, direction): 
        report = {'token': token, 'direction': direction}
        self.request('tank.request.turn', report)

    def fire_bullet(self, token):
        report = {'token': token}
        self.request('tank.request.fire', report) #If server responds with status 200 with message OK

#-------------------------CONSUMER-----------------
class ConsumerTank(Thread):

    def __init__(self, room_id):
        super().__init__() # allows us to access methods of the base class
        self.connection  = pika.BlockingConnection(pika.ConnectionParameters(host='34.254.177.17',port=5672,virtual_host='dar-tanks',credentials=pika.PlainCredentials(username='dar-tanks',password='5orPLExUYnyVYZg48caMpX')))
        self.channel = self.connection.channel()                      
        queue = self.channel.queue_declare(queue='',exclusive=True,auto_delete=True)
        queue_event = queue.method.queue
        self.channel.queue_bind(exchange='X:routing.topic',queue=queue_event,routing_key='event.state.' + room_id)
        self.channel.basic_consume(queue=queue_event, on_message_callback=self.on_response, auto_ack=True)
        self.response = None

    def on_response(self, ch, method, props, body):
        self.response = json.loads(body)
        # print(self.response)

    def run(self):
        self.channel.start_consuming()

UP = 'UP'
DOWN = 'DOWN'
LEFT = 'LEFT'
RIGHT = 'RIGHT'

directions = {
    pygame.K_w: UP,
    pygame.K_a: LEFT,
    pygame.K_s: DOWN,
    pygame.K_d: RIGHT
}


def draw_tank(x, y, width, direction, name, color):
    
    if direction == RIGHT:
        screen.blit(pygame.transform.rotate(taaanks, 270), (x, y), (0, 195 - width, 30, 28))
    if direction == LEFT:
        screen.blit(pygame.transform.rotate(taaanks, 90), (x, y), (0, 32 + width, 30, 28))
    if direction == UP:
        screen.blit(taaanks, (x, y), (195 - width, 0, 30, 28))
    if direction == DOWN:
        screen.blit(pygame.transform.rotate(taaanks, 180), (x, y), (35 + width, 0, 30, 28))

    NameShow = classic.render(name, True, (104, 2, 178))
    NameShowRect = NameShow.get_rect() 
    NameShowRect.center = (x + 5, y - 9)
    screen.blit(NameShow, NameShowRect)

def info(showtext, mode):

        gameover.play()
        screen.fill((195, 155, 255))
        if run == 0:
            lable = bigfont.render(showtext, True, (255, 255, 102))
            screen.blit(lable, (150,200)) 
            scoretxt = bigfont.render("SCORE:" + str(myscore), True, (0, 0, 0))
            screen.blit(scoretxt, (250, 350))
            pygame.display.flip()
            time.sleep(3)
            mode = False
            run = True
            welcome()
            pygame.display.flip()

def runmode2():
    global mode2, run, kickedlist, winlist, loselist, chosenroom, myscore
    client = TankRPC()
    client.server_test()
    client.registration(chosenroom)
    event_client = ConsumerTank(chosenroom)
    event_client.start()
    screen = pygame.display.set_mode((1000, 600))
    while mode2:
        screen.blit(backgroundImage4, (0, 0))
        screen.fill((255, 209, 210))
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                mode2 = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    mode2 = False
                if event.key in directions:
                    client.turn_tank(client.token, directions[event.key])
                if event.key == pygame.K_SPACE:
                    client.fire_bullet(client.token)

        kickedlist = event_client.response['kicked']
        winlist = event_client.response['winners']
        loselist = event_client.response['losers']
        try:
            round_time = event_client.response['remainingTime']
            txt = smallfont.render('ROUND WILL END IN ' + str(round_time) + 's', True, (20,20,0))
            if round_time <= 0:
                mode2 = False
                # client.connection.close()
                run = True
                welcome()
            txtRect = txt.get_rect()
            txtRect.center = (870, 20)
            screen.blit(txt, txtRect)

            bullets = event_client.response['gameField']['bullets']
            tanks = event_client.response['gameField']['tanks']
            start = 30
            pygame.draw.line(screen, (89, 6, 0), (800, 0), (800, 600), 5)
            pygame.draw.line(screen, (89, 6, 0), (995, 0), (995, 600), 5)
            scores = {tank['id']: [tank['score'],tank['health']] for tank in tanks}
            sorted_scores = reversed(sorted(scores.items(), key=lambda kv: kv[1]))
            for score in sorted_scores:
                if score[0] == name:
                    color = (152, 50, 15)
                else:
                    color = (47, 50, 210)
                teeext = smallfont.render(str(score[0]) + ': SCORE: ' + str(score[1][0]) + ' HP: ' + str(score[1][1]), True, color)
                teeextRect = teeext.get_rect()
                teeextRect.center = (870, start)
                screen.blit(teeext, teeextRect)
                start += 38
            for tank in tanks:
                t_x = tank['x']
                t_y = tank['y']
                tank_dir = tank['direction']
                tank_name = tank['id']
                if tank_name == name:
                    myscore = tank['score']
                    draw_tank(t_x, t_y, 0, tank_dir, 'MY TANK', (130, 16, 220))
                else:
                    draw_tank(t_x, t_y, 35, tank_dir, tank_name, (225, 1, 228))
            for bullet in bullets:
                bul_x = bullet['x']
                bul_y = bullet['y']
                if bullet['owner'] == client.tank_id:
                    pygame.draw.rect(screen, (255, 30, 30) , (bul_x, bul_y, 7, 7))
                else:
                    pygame.draw.rect(screen, (30, 30, 255) , (bul_x, bul_y, 7, 7))
            for tank in kickedlist:
                if client.tank_id == tank['tankId']:
                    info("You were kicked!", mode2)
            
            for tank in winlist:
                if client.tank_id == tank['tankId']:
                    info("You won!", mode2)

            for tank in loselist:
                if client.tank_id == tank['tankId']:
                    info("You lose!", mode2)
        except Exception as idk:
            pass
        pygame.display.flip()
    client.connection.close()
        

class Direction(Enum):
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4

#---------------------------------- T A N K ---------------------------------

class Tank:

    def __init__(self, x, y, color, mtd, d_right=pygame.K_RIGHT, d_left=pygame.K_LEFT, d_up=pygame.K_UP, d_down=pygame.K_DOWN):
        self.x = x
        self.y = y
        self.mtd = mtd
        self.bulcnt = 0
        self.speed = 5
        self.color = color
        self.width = 28
        self.life = 3
        self.life = 3
        self.images = [pygame.image.load('life_1.png'), pygame.image.load('life_2.png'), pygame.image.load('life_3.png')]
        self.direction = Direction.RIGHT

        self.KEY = {d_right: Direction.RIGHT, d_left: Direction.LEFT,
                    d_up: Direction.UP, d_down: Direction.DOWN}


    def show(self):
        if self.direction == Direction.RIGHT:
            screen.blit(pygame.transform.rotate(taaanks, 270), (self.x, self.y), (0, 195 - self.mtd, 30, 28))
            #screen.blit(taaanks, (self.x, self.y), (0, 160, 30, 28))

        elif self.direction == Direction.LEFT:
            screen.blit(pygame.transform.rotate(taaanks, 90), (self.x, self.y), (0, 32 + self.mtd, 30, 28))
            # screen.blit(pygame.transform.rotate(taaanks, 180), (self.x, self.y), (0, 160, 30, 28))

        elif self.direction == Direction.UP:
            screen.blit(taaanks, (self.x, self.y), (195 - self.mtd, 0, 30, 28))
            #screen.blit(pygame.transform.rotate(taaanks, 90), (self.x, self.y), (160, 0, 30, 28))

        elif self.direction == Direction.DOWN:
            screen.blit(pygame.transform.rotate(taaanks, 180), (self.x, self.y), (32 + self.mtd, 0, 30, 28))
            # screen.blit(pygame.transform.rotate(taaanks, 270), (self.x, self.y), (0, 160, 30, 28))


    def draw(self):
        tank_c = (self.x + 14, self.y + 14)
        pygame.draw.rect(screen, self.color,
                         (self.x, self.y, self.width, self.width), 7)
        pygame.draw.circle(screen, self.color, tank_c, 8)

        if self.direction == Direction.RIGHT:
            pygame.draw.line(screen, self.color, tank_c, (self.x + self.width + 12, self.y + 14), 5)

        elif self.direction == Direction.LEFT:
            pygame.draw.line(screen, self.color, tank_c, (self.x - 12, self.y + 14), 5)

        elif self.direction == Direction.UP:
            pygame.draw.line(screen, self.color, tank_c, (self.x + 14, self.y - 12), 5)

        elif self.direction == Direction.DOWN:
            pygame.draw.line(screen, self.color, tank_c, (self.x + 14, self.y + self.width + 12), 5)


    def change_direction(self, direction):
        self.direction = direction


    def move(self):
        if self.direction == Direction.LEFT:
            self.x -= self.speed
        if self.direction == Direction.RIGHT:
            self.x += self.speed
        if self.direction == Direction.UP:
            self.y -= self.speed
        if self.direction == Direction.DOWN:
            self.y += self.speed

        # self.draw
        self.show()


    def borders(self):
        if self.x > width or self.x < -30:
            self.x = (self.x + width) % width
        if self.y > height or self.y < -30:
            self.y = (self.y + height) % height
    

    def game_over(self):
        global mode1, run, seconds, walls_coors
        if self.life <= 0:
            gameover.play()
            screen.fill((195, 155, 255))
            if run == 0:
                screen.blit(gm, (150,50))
            pygame.display.flip()
            time.sleep(3)
            mode1 = False
            run = True
            seconds = 0
            welcome()
            self.life = 3
            walls_coors = [[216, 72], [240, 72], [264, 72], [288, 72], [312, 72], [336, 72], [360, 72], [384, 72], [408, 72], [432, 72], [456, 72], [480, 72], [504, 72], [528, 72], [552, 72], [576, 72], [600, 72], [624, 72], [216, 96], [624, 96], [216, 120], [624, 120], [216, 144], [624, 144], [360, 192], [384, 192], [408, 192], [432, 192], [456, 192], [480, 192], [504, 192], [360, 216], [384, 216], [408, 216], [432, 216], [456, 216], [480, 216], [504, 216], [216, 288], [624, 288], [216, 312], [624, 312], [216, 336], [624, 336], [216, 360], [240, 360], [264, 360], [288, 360], [312, 360], [336, 360], [360, 360], [384, 360], [408, 360], [432, 360], [456, 360], [480, 360], [504, 360], [528, 360], [552, 360], [576, 360], [600, 360], [624, 360], [168, 504], [192, 504], [216, 504], [240, 504], [264, 504], [288, 504], [312, 504], [336, 504], [360, 504], [216, 528], [240, 528], [264, 528], [288, 528], [312, 528], [240, 552], [264, 552], [288, 552], [216, 72], [240, 72], [264, 72], [288, 72], [312, 72], [336, 72], [360, 72], [384, 72], [408, 72], [432, 72], [456, 72], [480, 72], [504, 72], [528, 72], [552, 72], [576, 72], [600, 72], [624, 72], [216, 96], [624, 96], [216, 120], [624, 120], [216, 144], [624, 144], [360, 192], [384, 192], [408, 192], [432, 192], [456, 192], [480, 192], [504, 192], [360, 216], [384, 216], [408, 216], [432, 216], [456, 216], [480, 216], [504, 216], [216, 288], [624, 288], [216, 312], [624, 312], [216, 336], [624, 336], [216, 360], [240, 360], [264, 360], [288, 360], [312, 360], [336, 360], [360, 360], [384, 360], [408, 360], [432, 360], [456, 360], [480, 360], [504, 360], [528, 360], [552, 360], [576, 360], [600, 360], [624, 360], [168, 504], [192, 504], [216, 504], [240, 504], [264, 504], [288, 504], [312, 504], [336, 504], [360, 504], [216, 528], [240, 528], [264, 528], [288, 528], [312, 528], [240, 552], [264, 552], [288, 552]]

            self.x = random.randint(100,700)
            self.y = random.randint(100,500)
            
#------------------------------------B U L L E T---------------------------------

class Bullet:
    def __init__(self, x, y, dy, dx, d_space = pygame.K_SPACE):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.bul = False
        self.speed = 12

    def draw(self):
        pygame.draw.rect(screen, (30, 70, 30), (self.x, self.y, 10, 7))

    def move(self):
        if self.bul:
            self.x += self.dx
            self.y += self.dy
        self.draw()

    def borders(self):
        if self.x < -30 or self.x > width or self.y < -30 or self.y > height:
            self.bul = False
    

    def shooting(self, Tank):
        if Tank.direction == Direction.RIGHT:
            self.x = Tank.x + 50
            self.y = Tank.y + 18
            self.dx = self.speed
            self.dy = 0 

        if Tank.direction == Direction.LEFT:
            self.x = Tank.x - 15
            self.y = Tank.y + 15
            self.dx = -self.speed
            self.dy = 0 

        if Tank.direction == Direction.UP:
            self.x = Tank.x + 15
            self.y = Tank.y - 20
            self.dx = 0
            self.dy = -self.speed

        if Tank.direction == Direction.DOWN:
            self.x = Tank.x + 15
            self.y = Tank.y + 50
            self.dx = 0
            self.dy = self.speed

#---------------------TO SHOW LIFES------------------------------------------

def lifes (x, y, Tank, n, tx, ty):
    for i in range(3):
        if Tank.life == i + 1:
            screen.blit(Tank.images[i], (x, y))
    res = smallfont.render('PLAYER ' + str(n), True, (110, 30, 40))
    screen.blit(res, (tx, ty))


#-----------------CHECK COLLISION OF TANK AND BULLET---------------------

def collision(tank, bullet):
    if tank.x < bullet.x < tank.x + 30 and tank.y < bullet.y < tank.y + 30:
        hitsound.play()
        bullet.x = -100
        bullet.y = -100
        bullet.bul = False
        if tank.life > 1:
            explosion = Blowing((tank.x + 15, tank.y + 15), 'exp')
            sprites.add(explosion)
        return True
    return False

#----------------------SUPER POWER---------------------------
power_x = 400
power_y = 300
count_time = False

def super_power(tank, bullet):
    global power_show, power_y, power_x, timestop, ticks2, count_time

    if power_x - 15 < tank.x < power_x + 15 and power_y - 15 < tank.y < power_y + 15 and power_show:
        tank.speed = 12
        bullet.speed = 25
        power_show = False
        count_time = True
        power_x = -1000
        power_y = -1000
        global ticks2
        ticks2 = pygame.time.get_ticks()
    if count_time:
        timestop= (seconds - (ticks2 / 1000))
        if timestop > 5:
            bullet.speed = 12
            tank.speed = 5
            power_x = 200
            power_y = 300
    if seconds >= 6:
        if int(seconds % random.randint(3, 10)) == 0:
            power_show = True
    if power_show:
        screen.blit(power, (power_x,power_y))
    
power_show = False
allwalls = []

#-----------------------WALLS control----------------------
def control(tank, bullet):
    global life
    a = pygame.Rect(tank.x + 5, tank.y + 5, 28, 28)
    b = pygame.Rect(bullet.x + 12, bullet.y + 12, 5, 5)
    for i in walls_coors:
        if b.colliderect(pygame.Rect((i[0], i[1]), (24, 24))):
            walls_coors.remove(i)
            bullet.x = -100
            bullet.y = -100
        if a.colliderect(pygame.Rect((i[0], i[1]), (24, 24))):
            walls_coors.remove(i)
            life = True
            if life:
                tank.life -= 0.5
                life = False

#--------------------------MAIN FOR SINGLE MODE-----------------------------
tank1 = Tank(0, 1000,  (46,80,37), 0)
tank2 = Tank(0, 30,  (59,40,96), 35,  pygame.K_d, pygame.K_a, pygame.K_w, pygame.K_s)
tanks = [tank1, tank2]

bullet1 = Bullet(2000, 1000, 0, 0)
bullet2 = Bullet(2000, 1000, 0, 0, pygame.K_RETURN)
bullets = [bullet1, bullet2]

run = True
start_ticks=pygame.time.get_ticks()

#------------------------ROOMS--------------------

rooms = False

def clickbutton(x, y, r):
    global rooms, mode2, chosenroom, run, goinai, goinmulti, mode3
    mouse = pygame.mouse.get_pos()
    typing = pygame.mouse.get_pressed()

    if x + 100 > mouse[0] > x and y + 40 > mouse[1] > y:
        pygame.draw.line(screen, (255,255,255), (x + 3,y + 35), (x + 95, y + 35), 4)
        if typing[0] == 1:
            rooms = False
            run = False
            chosenroom = 'room-{}'.format(r)
            if goinmulti:
                mode2 = True
                runmode2()
            elif goinai:
                mode3 = True
                runmode3()

def roomsshow():
    global rooms, chosenroom
    while rooms:
        screen.blit(roomscreen, (0,0))
        for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    rooms = False
                    sys.exit()
        
        for i in range(5):
            clickbutton(35, 190 + i * 55, i + 1)

        for i in range(5):
            clickbutton(165, 190 + i * 55, i + 6)
        
        for i in range(5):
            clickbutton(290, 190 + i * 55, i + 11)
        
        for i in range(5):
            clickbutton(415, 190 + i * 55, i + 16)

        for i in range(5):
            clickbutton(540, 190 + i * 55, i + 21)
        
        for i in range(5):
            clickbutton(665, 190 + i * 55, i + 26)
            
        pygame.display.flip()

#-------------------------MULTIPLAYER AI - mode3--------------------------
def runmode3():
    global mode3, tank1, run, self_x, self_y, tank_x, tank_y
    client = TankRPC()
    client.server_test()
    client.registration(chosenroom)
    event_client = ConsumerTank(chosenroom)
    event_client.start()
    client.turn_tank(client.token, UP) 
    screen = pygame.display.set_mode((1000, 600))
    while mode3:
        screen.fill((255, 209, 210))
        screen.blit(backgroundImage4, (0, 0))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                mode3 = False
            if event.type == pygame.KEYDOWN:

                if event.key == pygame.K_ESCAPE:
                    mode3 = False
        
        kickedlist = event_client.response['kicked']
        winlist = event_client.response['winners']
        loselist = event_client.response['losers']
        try:
            round_time = event_client.response['remainingTime']
            txt = smallfont.render('ROUND WILL END IN ' + str(round_time) + 's', True, (20,20,0))
            if round_time <= 0:
                mode3 = False
                run = True
                welcome()
            txtRect = txt.get_rect()
            txtRect.center = (870, 20)
            screen.blit(txt, txtRect)
            bullets = event_client.response['gameField']['bullets']
            tanks = event_client.response['gameField']['tanks']
            start = 30
            pygame.draw.line(screen, (89, 6, 0), (800, 0), (800, 600), 5)
            pygame.draw.line(screen, (89, 6, 0), (995, 0), (995, 600), 5)
            scores = {tank['id']: [tank['score'],tank['health']] for tank in tanks}
            sorted_scores = reversed(sorted(scores.items(), key=lambda kv: kv[1]))
            for score in sorted_scores:
                if score[0] == name:
                    color = (152, 50, 15)
                else:
                    color = (47, 50, 210)
                teeext = smallfont.render(str(score[0]) + ': SCORE: ' + str(score[1][0]) + ' HP: ' + str(score[1][1]), True, color)
                teeextRect = teeext.get_rect()
                teeextRect.center = (870, start)
                screen.blit(teeext, teeextRect)
                start += 38
            for tank in tanks:
                tank_width = tank['width']
                tank_name = tank['id']
                if tank_name == name:
                    self_x = tank['x']
                    self_y = tank['y']
                    my_dir = tank['direction']
                    draw_tank(self_x, self_y, 0, my_dir,  'MY TANK', (130, 16, 220))
                else:
                    tank_direction = tank['direction']
                    tank_x = tank['x']
                    tank_y = tank['y']
                    draw_tank(tank_x, tank_y, 35, tank_direction, tank_name, (225, 200, 228))

                    if tank_x in range(self_x - 70, self_x + 70) and tank_y in range(self_y - 70, self_y + 70):
                        if tank.direction == 'UP':
                            client.turn_tank(client.token, RIGHT)
                        elif tank.direction == 'LEFT':
                            client.turn_tank(client.token, UP)
                        elif tank.direction == 'RIGHT':
                            client.turn_tank(client.token, DOWN)
                        elif tank.direction == 'DOWN':
                            client.turn_tank(client.token, LEFT)

                    if tank_x in range(self_x - 100, self_x + 100):
                        if (my_dir == 'UP' and (tank_direction == 'DOWN' or tank_direction == 'UP' or tank_direction == 'LEFT') and self_y > tank_y) or (my_dir == 'DOWN' and (tank_direction == 'UP' or tank_direction == 'LEFT') and self_y < tank_y):
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, RIGHT) 
                        elif ((my_dir == 'UP' and (tank_direction == 'DOWN' or tank_direction == 'UP') and self_y < tank_y) or (((my_dir == 'DOWN' and tank_direction == 'UP') or (my_dir == 'DOWN' and tank_direction == 'DOWN') or (my_dir == 'DOWN' and tank_direction == 'LEFT')) and self_y > tank_y)):
                            client.turn_tank(client.token, UP) 
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, RIGHT) 
                        elif (my_dir == 'DOWN' and tank_direction == 'RIGHT' and self_y < tank_y) or (my_dir == 'UP' and tank_direction == 'RIGHT' and self_y > tank_y):
                            client.fire_bullet(client.token) 
                            client.turn_tank(client.token, LEFT)
                        elif my_dir == 'DOWN' and tank_direction == 'RIGHT' and self_y > tank_y:
                            client.turn_tank(client.token,  UP)
                            client.fire_bullet(client.token) 
                            client.turn_tank(client.token, LEFT)
                        elif my_dir == 'UP' and tank_direction == 'RIGHT' and self_y < tank_y:
                            client.turn_tank(client.token,  DOWN)
                            client.fire_bullet(client.token) 
                            client.turn_tank(client.token, LEFT)
                        elif my_dir == 'UP' and tank_direction == 'LEFT' and self_y < tank_y:
                            client.turn_tank(client.token,  DOWN)
                            client.fire_bullet(client.token) 
                            client.turn_tank(client.token, RIGHT)
                        elif my_dir == 'RIGHT' and (tank_direction == 'LEFT' or tank_direction == 'RIGHT' or tank_direction == 'DOWN' ) and self_x > tank_x:
                            client.turn_tank(client.token, LEFT)
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, UP) 
                        elif (my_dir == 'RIGHT' and (tank_direction == 'LEFT' or tank_direction == 'DOWN') and self_x < tank_x) or (my_dir == 'LEFT' and (tank_direction == 'LEFT' or tank_direction == 'DOWN') and self_x > tank_x):
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, UP)
                        elif (my_dir == 'LEFT' and (tank_direction == 'LEFT' or tank_direction == 'RIGHT') and self_x < tank_x) or (my_dir == 'LEFT' and tank_direction == 'DOWN' and self_x < tank_x):
                            client.turn_tank(client.token, RIGHT)
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, UP)
                        elif (my_dir == 'LEFT' and (tank_direction == 'RIGHT' or tank_direction == 'UP') and self_x > tank_x) or (my_dir == 'RIGHT' and (tank_direction == 'UP' or tank_direction == 'RIGHT')and self_x < tank_x):
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, DOWN)
                        elif my_dir == 'RIGHT' and tank_direction == 'UP' and self_x > tank_x :
                            client.turn_tank(client.token, LEFT) 
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, DOWN)
                        elif my_dir == 'LEFT' and tank_direction == 'UP' and self_x < tank_x :
                            client.turn_tank(client.token, RIGHT)
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, DOWN)

                    if tank_y in range(self_y - 80, self_y + 80):
                        if (my_dir == 'UP' and (tank_direction == 'DOWN' or tank_direction == 'UP' or tank_direction == 'RIGHT') and self_y > tank_y) or (my_dir == 'DOWN' and (tank_direction == 'DOWN' or tank_direction == 'LEFT' or tank_direction == 'RIGHT' or tank_direction == 'UP') and self_y < tank_y):
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, RIGHT) 
                        elif ((my_dir == 'UP' and (tank_direction == 'DOWN' or tank_direction == 'UP' or tank_direction == 'RIGHT')) or (my_dir == 'RIGHT' and (tank_direction == 'LEFT' or tank_direction == 'RIGHT') and self_y < tank_y)):
                            client.turn_tank(client.token, DOWN) 
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, LEFT)
                        elif my_dir == 'DOWN' and self_y > tank_y:
                            client.turn_tank(client.token,  UP)
                            client.fire_bullet(client.token) 
                            client.turn_tank(client.token, RIGHT)
                        elif (my_dir == 'UP' or tank_direction == 'LEFT') and tank_direction == 'LEFT' and self_y > tank_y:
                            client.fire_bullet(client.token) 
                            client.turn_tank(client.token, UP)
                        elif my_dir == 'UP' and tank_direction == 'LEFT' and self_y < tank_y:
                            client.turn_tank(client.token,  DOWN)
                            client.fire_bullet(client.token) 
                            client.turn_tank(client.token, UP)
                        if my_dir == 'RIGHT'  and self_x > tank_x:
                            client.turn_tank(client.token, LEFT)
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, UP)
                        elif my_dir == 'LEFT' and (tank_direction == 'DOWN' or tank_direction == 'RIGHT' or tank_direction == 'LEFT') and self_x < tank_x:
                            client.turn_tank(client.token, RIGHT)
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, UP)
                        elif (my_dir == 'LEFT' and (tank_direction == 'RIGHT' or tank_direction == 'UP') and self_x > tank_x) or (my_dir == 'RIGHT' and tank_direction == 'UP' and self_x < tank_x):
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, DOWN)
                        elif (my_dir == 'RIGHT' and tank_direction == 'DOWN' and self_x < tank_x) or (my_dir == 'LEFT' and tank_direction == 'DOWN' and self_x > tank_x):
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, UP)
                        elif my_dir == 'LEFT' and tank_direction == 'UP' and self_x < tank_x :
                            client.turn_tank(client.token, RIGHT)
                            client.fire_bullet(client.token)
                            client.turn_tank(client.token, DOWN)

            for bullet in bullets:
                if tank_name == name:
                    mybul_x = bullet['x']
                    mybul_y = bullet['y']
                    pygame.draw.circle(screen, (0, 230, 30) , (mybul_x, mybul_y), 4)
                else:
                    bullet_x = bullet['x']
                    bullet_y = bullet['y']
                    pygame.draw.circle(screen, (230, 30, 0) , (bullet_x, bullet_y), 4)
                    if bullet_x in range(self_x, self_x + 50) and (self_y<tank_y or self_y>tank_y):
                        client.turn_tank(client.token, 'RIGHT')
                    if bullet_y in range(self_y, self_y + 50) and (self_x<tank_x or self_x>tank_x):
                        client.turn_tank(client.token, 'UP')           

            for tank in kickedlist:
                if client.tank_id == tank['tankId']:
                    info("You were kicked!", mode3)
            for tank in winlist:
                if client.tank_id == tank['tankId']:
                    info("You won!", mode3)
            for tank in loselist:
                if client.tank_id == tank['tankId']:
                    info("You lose!", mode3)
        except Exception as idk:
            pass
        pygame.display.flip()
    client.connection.close()
#--------------------------------MAIN MENU--------------------------------------
def welcome():
    global mode1, mode2, rooms, mode3, goinmulti, goinai, run
    screen = pygame.display.set_mode((800, 600))
    while run:
            screen.blit(menu, (0,-5))
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    run = False

            mouse = pygame.mouse.get_pos()
            typing = pygame.mouse.get_pressed()

            #------------------------S T A R T button----------------------

            if 150 + 100 > mouse[0] > 150 and 450 + 50 > mouse[1] > 450:
                pygame.draw.rect(screen, (170,25,30),(150,450,100,50))
                if typing[0] == 1:
                    mode1 = True
                    run = False
            else:
                pygame.draw.rect(screen, (110, 30, 40),(150,450,100,50))

            #----------------------E X I T button--------------------------

            if 550 + 100 > mouse[0] > 550 and 450 + 50 > mouse[1] > 450:
                pygame.draw.rect(screen, (170, 29, 34), (550,450,100,50))
                if typing[0] == 1: #and action != None:
                    mode1 = False
                    run = False
                    mode3 = False
                    mode2 = False
                    sys.exit()
            else:
                pygame.draw.rect(screen, (110, 30, 40), (550,450,100,50))
            

                
            #---------------------Single player mode--------------------------

            if 100 + 120 > mouse[0] > 100 and 270 + 50 > mouse[1] > 270:
                pygame.draw.rect(screen, (255,125,0), (100, 270, 120, 50))
                if typing[0] == 1: #and action != None:
                    mode1 = True
                    run = False
                    mode2 = False
                    mode3 = False
            else:
                pygame.draw.rect(screen, (255,180,0), (100, 270, 120, 50))
            easy = smallfont.render('Single player', True,  (33,64,95))
            screen.blit(easy, (100, 275))

            #---------------------Multiplayer mode----------------------

            if 350 + 100 > mouse[0] > 350 and 270 + 50 > mouse[1] > 270:
                pygame.draw.rect(screen, (255,125,0), (350, 270, 115, 50))
                if typing[0] == 1: #and action != None:
                    run = False
                    goinmulti = True
                    rooms = True
                    roomsshow()
                    mode2 = False
                    mode1 = False
                    mode3 = False
            else:
                pygame.draw.rect(screen, (255,180,0), (350, 270, 115, 50))
            med = smallfont.render('Multiplayer', True, (33,64,95))
            screen.blit(med, (358, 275))

            #--------------------Multiplayer AI mode-------------------------------

            if 600 + 100 > mouse[0] > 600 and 270 + 50 > mouse[1] > 270:
                pygame.draw.rect(screen, (255,125,0), (600, 270, 145, 50)) 
                if typing[0] == 1: #and action != None:
                    run = False
                    goinai = True
                    mode3 = False
                    rooms = True
                    roomsshow()
                    mode2 = False
                    mode1 = False
                    pygame.display.flip()
            else:
                pygame.draw.rect(screen, (255,180,0), (600, 270, 145, 50))
            hard = smallfont.render('Multiplayer AI', True, (33,64,95))
            screen.blit(hard, (605, 275))
            
        #-----------------NAME of the buttons------------------------------

            go = smallfont.render('START', True, (255, 255, 255))
            screen.blit(go, (167, 457))

            ex = smallfont.render('EXIT', True, (255, 255, 255))
            screen.blit(ex, (575, 457))

            screen.blit(pl, (320,400))
            pygame.display.flip()

welcome()
walls_coors = [[216, 72], [240, 72], [264, 72], [288, 72], [312, 72], [336, 72], [360, 72], [384, 72], [408, 72], [432, 72], [456, 72], [480, 72], [504, 72], [528, 72], [552, 72], [576, 72], [600, 72], [624, 72], [216, 96], [624, 96], [216, 120], [624, 120], [216, 144], [624, 144], [360, 192], [384, 192], [408, 192], [432, 192], [456, 192], [480, 192], [504, 192], [360, 216], [384, 216], [408, 216], [432, 216], [456, 216], [480, 216], [504, 216], [216, 288], [624, 288], [216, 312], [624, 312], [216, 336], [624, 336], [216, 360], [240, 360], [264, 360], [288, 360], [312, 360], [336, 360], [360, 360], [384, 360], [408, 360], [432, 360], [456, 360], [480, 360], [504, 360], [528, 360], [552, 360], [576, 360], [600, 360], [624, 360], [168, 504], [192, 504], [216, 504], [240, 504], [264, 504], [288, 504], [312, 504], [336, 504], [360, 504], [216, 528], [240, 528], [264, 528], [288, 528], [312, 528], [240, 552], [264, 552], [288, 552], [216, 72], [240, 72], [264, 72], [288, 72], [312, 72], [336, 72], [360, 72], [384, 72], [408, 72], [432, 72], [456, 72], [480, 72], [504, 72], [528, 72], [552, 72], [576, 72], [600, 72], [624, 72], [216, 96], [624, 96], [216, 120], [624, 120], [216, 144], [624, 144], [360, 192], [384, 192], [408, 192], [432, 192], [456, 192], [480, 192], [504, 192], [360, 216], [384, 216], [408, 216], [432, 216], [456, 216], [480, 216], [504, 216], [216, 288], [624, 288], [216, 312], [624, 312], [216, 336], [624, 336], [216, 360], [240, 360], [264, 360], [288, 360], [312, 360], [336, 360], [360, 360], [384, 360], [408, 360], [432, 360], [456, 360], [480, 360], [504, 360], [528, 360], [552, 360], [576, 360], [600, 360], [624, 360], [168, 504], [192, 504], [216, 504], [240, 504], [264, 504], [288, 504], [312, 504], [336, 504], [360, 504], [216, 528], [240, 528], [264, 528], [288, 528], [312, 528], [240, 552], [264, 552], [288, 552]]

#--------------------------------M A I N   L O O P--------------------------------

mymap = """
    ___________________________
    ___________________________
    _____##################____
    _____#________________#____
    _____#________________#____
    _____#________________#____
    ___________________________
    ___________#######_________
    ___________#######__________
    ___________________________
    ___________________________
    _____#________________#___
    _____#________________#____
    _____#________________#__
    _____##################__
    _________________________
    _________________________
    _________________________
    _________________________
    _________________________
    ___#########_____________
    _____#####_______________
    ______###________________
"""
wallim = pygame.image.load('wall.png')
mymap = mymap.splitlines()

entities = pygame.sprite.Group()
platforms = []

#--------------------SINGLE-------------
while mode1:
    seconds=(pygame.time.get_ticks()-start_ticks)/1000
    screen.blit(backgroundImage4, (0, 0))
    millis = timetick.tick(FPS)
    # for y, line in enumerate(mymap):
    #     for x, c in enumerate(line):
    #         if c == "#":
    #             # pf = Platform(x * 25, y * 25)
    #             # # pf = pygame.Surface((24,24))
    #             # # pf.fill(pygame.Color((244,164,96))) 
    #             # # screen.blit(pf,(x * 25,y * 25))
    #             # entities.add(pf)
    #             # platforms.append(pf)

    #             screen.blit(wallim, (x * 24, y * 24))
    #             allwalls.append([x * 24, y * 24])
    
    for i in walls_coors:
        screen.blit(wallim, (i[0], i[1]))                
    sprites.update()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            mode1 = False
        if event.type == pygame.KEYDOWN:
            if event.key in tank1.KEY.keys():
                tank1.change_direction(tank1.KEY[event.key])
            if event.key in tank2.KEY.keys():
                tank2.change_direction(tank2.KEY[event.key])
            if event.key == pygame.K_SPACE and bullet1.bul == False:
                    bullet1.bul = True
                    shootsound.play()
                    bullet1.shooting(tank1)
            if event.key == pygame.K_RETURN and bullet2.bul == False:
                    bullet2.bul = True
                    shootsound.play()
                    bullet2.shooting(tank2)
            if event.key == pygame.K_ESCAPE: 
                mode1 = False
                sys.exit()

    if collision(tank1, bullet2):
        tank1.life -=1
    if collision(tank2, bullet1):
        tank2.life -=1

    for tank in tanks:
        tank.move()
        if tank.game_over():
            tank.life = 3
        tank.borders()
        lifes(15, 35, tank1, 1, 15, 5)
        lifes(width - 100, 35, tank2, 2, width - 100, 5)
    
    entities.draw(screen)
    bullet1.move()
    bullet2.move()
    super_power(tank1, bullet1)
    super_power(tank2, bullet2)
    bullet1.borders()
    bullet2.borders()
    control(tank1, bullet1)
    control(tank2, bullet2)
    sprites.draw(screen)
    pygame.display.flip()

font = pygame.font.Font('freesansbold.ttf', 32)
pygame.quit()