from django.db import models
from django.core.exceptions import ValidationError

class ComponentType(models.TextChoices):
  VEHICLE = 'VEH', 'Vehicle'
  LOCATION = 'LOC', 'Location'

class Component(models.Model):
  type = models.CharField(max_length=3, choices=ComponentType.choices, default=ComponentType.VEHICLE)
  steam_id = models.IntegerField(default=0,blank=True)
  component_version = models.CharField(default="1.0", max_length=20)
  component_name= models.CharField(default="Example_Mod", max_length=200)
  do_update = models.BooleanField(default=False)
  short_name = models.CharField(default="", max_length=200)
  def __str__(self):
    return "{} {} ({})".format(self.type, self.component_name, self.component_version)

class RaceConditions(models.Model):
  description = models.TextField(default="Add description")
  rfm = models.FileField()
  def __str__(self):
    return "{} ({})".format(self.description, self.rfm)

class Track(models.Model):
  component = models.ForeignKey(Component, on_delete=models.DO_NOTHING)
  layout = models.CharField(default="", blank=False, max_length=200)
  def __str__(self):
    return "{}@{}".format(self.layout, self.component)
  
class Entry(models.Model):
  component = models.ForeignKey(Component, on_delete=models.DO_NOTHING)
  team_name = models.CharField(default="Example Team", max_length=200)
  vehicle_number = models.IntegerField(default=1)
  def __str__(self):
    return "{}#{} ({})".format(self.team_name, self.vehicle_number, self.component)

class Event(models.Model):
  overwrites_multiplayer = models.TextField(default="{}")
  overwrites_player = models.TextField(default="{}")
  name = models.CharField(default="", max_length=200)
  conditions = models.ForeignKey(RaceConditions, on_delete=models.DO_NOTHING)
  entries = models.ManyToManyField(Entry)
  tracks = models.ManyToManyField(Track)
  def __str__(self):
    return "{}".format(self.name)

class ServerStatus(models.TextChoices):
  STARTREQUESTED = 'S+', 'Start'
  STOPREQUESTED = 'R-', 'Stop'
  DEPLOY = 'D', 'Change config'


class Server(models.Model):
  url = models.CharField(blank=False, max_length=500, default='')
  secret = models.CharField(blank=False, max_length=500, default='')
  public_ip = models.CharField(blank=False, max_length=500, default='')
  build_path =  models.CharField(blank=False, max_length=500, default='')
  packs_path =  models.CharField(blank=False, max_length=500, default='')
  event = models.ForeignKey(Event, on_delete=models.DO_NOTHING, blank=True, null=True)
  action = models.CharField(max_length=3, choices=ServerStatus.choices, blank=True, default='')
  
  def __str__(self):
    return self.url