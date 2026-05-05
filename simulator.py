import pg8000, time, random, requests

# Database configuration targeting Port 5056[cite: 2]
DB_CONFIG = {
    "user": "postgres", 
    "password": "gis1234", 
    "host": "127.0.0.1", 
    "database": "assets_tracker", 
    "port": 5056
}

def get_road_point(lon, lat):
    """Snaps a raw coordinate to the nearest valid road using OSRM."""
    url = f"http://router.project-osrm.org/nearest/v1/driving/{lon},{lat}"
    try:
        r = requests.get(url).json()
        # Returns the snapped [longitude, latitude] from the OSRM waypoints[cite: 1]
        return r['waypoints'][0]['location'] 
    except:
        return [lon, lat]

def simulate_roads():
    """Main simulation loop that updates vehicle positions every 5 seconds[cite: 1]."""
    conn = None
    try:
        conn = pg8000.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("Road Simulation Started (Port 5056)...")
        
        while True:
            # Only fetch assets categorized as 'vehicle' for movement
            cur.execute("SELECT id, ST_X(geom), ST_Y(geom) FROM assets WHERE asset_type ILIKE 'vehicle'")
            vehicles = cur.fetchall()
            
            for v in vehicles:
                # 1. Generate a small random movement offset[cite: 1]
                target_lon = float(v[1]) + random.uniform(-0.0005, 0.0005)
                target_lat = float(v[2]) + random.uniform(-0.0005, 0.0005)
                
                # 2. Snap the new coordinate to a road network[cite: 1]
                road_lon, road_lat = get_road_point(target_lon, target_lat)
                
                # 3. Update the PostGIS geometry and timestamp
                cur.execute("""
                    UPDATE assets 
                    SET geom=ST_SetSRID(ST_MakePoint(%s, %s), 4326), last_seen=NOW() 
                    WHERE id=%s
                """, (road_lon, road_lat, v[0]))
            
            conn.commit()
            # Wait 5 seconds to match the frontend polling interval
            time.sleep(5)
            
    except Exception as e:
        print(f"Simulator Error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    simulate_roads()