from mpl_toolkits.basemap import Basemap
from datetime import datetime
from calendar import month_name
from haversine import haversine
from tqdm import tqdm
import time
import json
import os

# Ignore warnings
import warnings
warnings.filterwarnings('ignore')

# Load configuration
import configparser
config = configparser.ConfigParser(
    comment_prefixes=(';'),
    inline_comment_prefixes=(';'))
config.read('config.ini')

# Define rendering configuration
dpi = 120
fps = int(config['render']['fps'])
pltw = int(config['render']['resolution_w'])
plth = int(config['render']['resolution_h'])

# Set up logging
import logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('mappr')
if config['processing'].getboolean('debug'):
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.WARNING)

# Initialize the figure
logger.info('Initializing figure...')
import matplotlib.pyplot as plt
fig = plt.figure(figsize=(pltw // dpi, plth // dpi))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_aspect(plth/pltw, adjustable='datalim')
plt.tight_layout()
color = config['colors']

# Create a Basemap object
logger.info('Creating a Basemap object...')
resolution = ((('h' if pltw > 1280 else 'i') if pltw > 640 else 'l') if pltw > 320 else 'c')
basemap = Basemap(projection='merc',lat_ts=20,resolution=resolution,epsg=4326)
if config['map'].getboolean('use_arcgis'):
    basemap.arcgisimage(service='World_Street_Map',xpixels=pltw)
if config['map'].getboolean('use_etopo'):
    basemap.etopo(alpha=0.25)
if config['map'].getboolean('use_fill'):
    basemap.drawmapboundary(linewidth=0,fill_color=color['water'])
    basemap.fillcontinents(color=color['grass'], lake_color=color['water'])
basemap_states = [basemap.drawstates()]
basemap_countries = [basemap.drawcountries()]

# Define Basemap bounds
logger.info('Defining Basemap bounds...')
lonmin, latmin = (-180, -80)
lonmax, latmax = (180, 80)
bound = lambda _x,_l,_h: min(max(_x,_l),_h)
xmin, ymin = basemap(lonmin, latmin)
xmax, ymax = basemap(lonmax, latmax)
ymax = min(ymax,xmax*plth/pltw)

# Create a legend
logger.info('Creating a legend...')
import matplotlib.patches as mpatches
legend = []
legend.append(mpatches.Patch(color=color['drive'], label='By Car / On Foot'))
legend.append(mpatches.Patch(color=color['train'], label='By Train'))
legend.append(mpatches.Patch(color=color['plane'], label='By Plane'))
plt.legend(handles=legend, loc="lower right", fontsize=plth//40)

# Import place data
logger.info('Importing place data...')
with open(os.path.join(config['data']['folder'], 'places.json'), 'r') as _file_places:
    data_places = json.load(_file_places)

# Import location data
logger.info('Importing location data...')
data = []
hist_places = {}
for _dir, _, _files in os.walk(os.path.join(config['data']['folder'], config['data']['year'])):
    for _file in _files:
        with open(os.path.join(_dir, _file), 'r') as _input:
            _locations = json.load(_input)['locations']
            for _i, _d in enumerate(_locations):
                _d['iframe'] = _i
                _d['zoom'] = float(config['map']['zoom'])
                _d['time'] = int(_d['timestampMs']) // 1000
                _d['lat'] = _d['latitudeE7'] / 10000000
                _d['lon'] = _d['longitudeE7'] / 10000000
                _d['x'], _d['y'] = basemap(_d['lon'],_d['lat'])
                _date = datetime.fromtimestamp(_d['time'])
                _d['date'] = '{} {}, {}'.format(
                    month_name[_date.month], _date.day, _date.year)
                _coordinate = (_d['lat'], _d['lon'])
                _nearest = min(data_places, key=lambda _x:
                               haversine((_x['lat'], _x['lon']), _coordinate, miles=True))
                if haversine((_nearest['lat'], _nearest['lon']), _coordinate, miles=True) < 20:
                    _d['place'] = _nearest['name']
                    _d['type'] = _nearest['type']
                else:
                    _d['place'] = None
                    _d['type'] = None
                hist_places[_d['place']] = hist_places.get(_d['place'], 0) + 1
                _d['interpolated'] = False
                _d['status'] = "drive"
                del _d['timestampMs']
                del _d['latitudeE7']
                del _d['longitudeE7']
            data.extend(_locations)
data = sorted(data, key=lambda _k: _k['time'])
logger.info('Frames imported = {}'.format(len(data)))

# Scrub consecutive data points in one place
if config['processing'].getboolean('scrub'):
    _last = None
    _i = _count = 0
    _hist_scrub = {}
    while _i < len(data):
        if data[_i]['place']:
            if _last != data[_i]['place']:
                _count = 1
                _last = data[_i]['place']
            else:
                _count += 1
            if _count > (fps*3):
                _hist_scrub[_last] = _hist_scrub.get(_last, 0) + 1
                del data[_i]
        _i += 1
    # logger.info('Scrubbed '+''.join(['{} frames from {}{}'.format(
    #             _hist_scrub[_k],_k,((', ' if _i < len(_hist_scrub) - 2 else ', and ')
    #             if _i < len(_hist_scrub) - 1 else '.')
    #             ) for _i, _k in enumerate(_hist_scrub)]))
    logger.info('Frames after scrubbing = {}'.format(len(data)))

# Initialize frame text
def status(_d):
    if _d['place']:
        return _d['place']
    else:
        if _d['status'] == "drive":
            return "Driving..."
        if _d['status'] == "train":
            return "Riding the train..."
        if _d['status'] == "plane":
            return "Flying..."

logger.info('Initializing frame text...')
frame_date_image = plt.imread('icons/calendar.png')
frame_status_image = plt.imread('icons/{}.png'.format(data[0]['status']))
frame_date_artist = ax.imshow(frame_date_image, alpha=1, aspect='equal',
                            extent=[0.02, .08*plth/pltw, 0.06, .11],
                            zorder=3, transform=ax.transAxes)
frame_status_artist = ax.imshow(frame_status_image, alpha=1, aspect='equal',
                            extent=[0.02, .08*plth/pltw, 0.13, .18],
                            zorder=3, transform=ax.transAxes)
frame_date_text = ax.text(0.057, 0.07, data[0]['date'], color='black', fontsize=plth//40, transform=ax.transAxes)
frame_status_text_placeholder = status(data[0])
frame_status_text = ax.text(0.057, 0.14, frame_status_text_placeholder, color='black', fontsize=plth//40, transform=ax.transAxes)

# Define View bounds
logger.info('Defining View bounds...')
lon, lat = (data[0]['lon'], data[0]['lat'])
lonz = data[0]['zoom']
latz = lonz * plth / pltw
lonl, lonh = (bound(lon-lonz,lonmin,lonmax), bound(lon+lonz,lonmin,lonmax))
latl, lath = (bound(lat-latz,latmin,latmax), bound(lat+latz,latmin,latmax))
xl, yl = basemap(lon-lonz, lat-latz)
xh, yh = basemap(lon+lonz, lat+latz)
xl = bound(xl,xmin,xmax)
xh = bound(xh,xmin,xmax)
yl = bound(yl,ymin,ymax)
yh = bound(yh,ymin,ymax)
ax.set_xlim([xl, xh])
ax.set_ylim([yl, yh])

# Place locations on the map
logger.info('Placing locations on the map...')
map_places = []
for i, c in enumerate(data_places):
    cx, cy = basemap(c['lon'],c['lat'])
    map_places.append(ax.plot(cx,cy,
        color=color['place'],
        marker='o',snap=True,
        markersize=6)[0])
    map_places.append(ax.text(s=c['name'],
        x=cx-0.075,y=cy+0.075,zorder=3,
        horizontalalignment='right',
        multialignment='center',
        color="black",alpha=1,fontsize=plth//50))

# Array for trail
map_trail = []

# Render a frame
def render(frame_index):

    _i = bound(frame_index-frames_before,1,len(data))
    _p = bound(frame_index-frames_before-1,0,len(data))

    # Determine meridian coordinates of this frame and the previous frame
    lon, lat = (data[_i]['lon'], data[_i]['lat'])
    lonp, latp = (data[_p]['lon'], data[_p]['lat'])
    x, y = (data[_i]['x'], data[_i]['y'])
    xp, yp = (data[_p]['x'], data[_p]['y'])

    # Adjust view bounds
    lonz = data[_i]['zoom']
    latz = lonz * plth / pltw
    lonl, lonh = (bound(lon-lonz,lonmin,lonmax), bound(lon+lonz,lonmin,lonmax))
    latl, lath = (bound(lat-latz,latmin,latmax), bound(lat+latz,latmin,latmax))
    xl, yl = basemap(lon-lonz, lat-latz)
    xh, yh = basemap(lon+lonz, lat+latz)
    xl = bound(xl,xmin,xmax)
    xh = bound(xh,xmin,xmax)
    yl = bound(yl,ymin,ymax)
    yh = bound(yh,ymin,ymax)
    ax.set_xlim([xl, xh])
    ax.set_ylim([yl, yh])

    # Draw a trail from the previous point to the current point
    map_trail.append(basemap.plot([x, xp], [y, yp], color=color[data[_i]['status']], linewidth=2)[0])

    # Update frame text
    frame_date_text.set_text(data[_i]['date'])
    frame_status_artist.set_data(plt.imread('icons/{}.png'.format(data[_i]['status'])))
    frame_status_text.set_text(status(data[_i]))

    # Update rendering progress bar
    global pbar
    pbar.update()

    return ax, map_trail, frame_date_text, frame_status_text, frame_status_artist


# Compute the number of frames to animate
frames_before = fps * int(config['render']['time_before'])
frames_zoom =  fps * int(config['render']['time_zoom'])
frames_after = fps * int(config['render']['time_after'])
frames_total = frames_before + len(data) + frames_zoom + frames_after
frames = range(frames_before+350,frames_before+590)

# Create and save animation
logger.info('Rendering...')
pbar = tqdm(total=len(frames),unit='frames')
import matplotlib.animation as animation
anim = animation.FuncAnimation(fig, render, frames=frames)
writer = animation.writers['ffmpeg'](fps=fps)
anim.save('map_' + str(int(time.time())) + '.mp4', dpi=dpi, writer=writer)
pbar.close()

## Report stats
print("Top 3 Places Visited:")
top_cities = [(hist_places[k], k) for k in sorted(hist_places, key=hist_places.get, reverse=True) if k is not None]
print("\t1st >>", top_cities[0][1], "\n", "\t2nd >>", top_cities[1][1], "\n", "\t3rd >>", top_cities[2][1])