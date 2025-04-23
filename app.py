import streamlit as st
import sqlite3
import pandas as pd
import folium
from streamlit_folium import folium_static
import uuid
import math
import plotly.express as px
import plotly.graph_objects as go

# Initialize SQLite database
def init_db():
    with sqlite3.connect('emissions.db') as conn:
        c = conn.cursor()
        # Create suppliers table
        c.execute('''CREATE TABLE IF NOT EXISTS suppliers 
                    (id TEXT PRIMARY KEY, supplier_name TEXT, country TEXT, city TEXT, 
                     material TEXT, green_score INTEGER, annual_capacity_tons INTEGER)''')
        # Create emissions table
        c.execute('''CREATE TABLE IF NOT EXISTS emissions 
                    (id TEXT PRIMARY KEY, source TEXT, destination TEXT, 
                     transport_mode TEXT, distance_km REAL, co2_kg REAL, 
                     weight_tons REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        # Insert expanded supplier data
        sample_suppliers = [
            # United Kingdom - London
            (str(uuid.uuid4()), 'UK Steel Co', 'United Kingdom', 'London', 'Steel', 85, 50000),
            (str(uuid.uuid4()), 'London Tech Supplies', 'United Kingdom', 'London', 'Electronics', 70, 20000),
            (str(uuid.uuid4()), 'British Textiles Ltd', 'United Kingdom', 'London', 'Textiles', 65, 30000),
            # France - Paris
            (str(uuid.uuid4()), 'French Steelworks', 'France', 'Paris', 'Steel', 80, 45000),
            (str(uuid.uuid4()), 'Paris Electronics Hub', 'France', 'Paris', 'Electronics', 75, 25000),
            (str(uuid.uuid4()), 'ChemFrance', 'France', 'Paris', 'Chemicals', 60, 40000),
            # USA - New York
            (str(uuid.uuid4()), 'American Steel Corp', 'USA', 'New York', 'Steel', 75, 60000),
            (str(uuid.uuid4()), 'NY Tech Innovate', 'USA', 'New York', 'Electronics', 80, 30000),
            (str(uuid.uuid4()), 'US Textile Giants', 'USA', 'New York', 'Textiles', 70, 35000),
            # China - Shanghai
            (str(uuid.uuid4()), 'China Steel Group', 'China', 'Shanghai', 'Steel', 65, 80000),
            (str(uuid.uuid4()), 'Shanghai Electronics', 'China', 'Shanghai', 'Electronics', 60, 50000),
            (str(uuid.uuid4()), 'EastChem Co', 'China', 'Shanghai', 'Chemicals', 55, 60000),
            # Japan - Tokyo
            (str(uuid.uuid4()), 'Nippon Steel', 'Japan', 'Tokyo', 'Steel', 80, 55000),
            (str(uuid.uuid4()), 'Tokyo Tech Solutions', 'Japan', 'Tokyo', 'Electronics', 85, 40000),
            (str(uuid.uuid4()), 'Japan Textiles', 'Japan', 'Tokyo', 'Textiles', 70, 30000),
            # Australia - Sydney
            (str(uuid.uuid4()), 'Aussie Steelworks', 'Australia', 'Sydney', 'Steel', 75, 40000),
            (str(uuid.uuid4()), 'Sydney Chem Supplies', 'Australia', 'Sydney', 'Chemicals', 65, 35000),
            (str(uuid.uuid4()), 'Aus Textiles', 'Australia', 'Sydney', 'Textiles', 70, 25000)
        ]
        c.executemany('INSERT OR IGNORE INTO suppliers VALUES (?, ?, ?, ?, ?, ?, ?)', sample_suppliers)
        conn.commit()

# DEFRA-based emission factors (kg CO₂ per km per ton)
EMISSION_FACTORS = {
    'Truck': 0.096,  # HGV, diesel
    'Train': 0.028,  # Freight train
    'Ship': 0.016,  # Container ship
    'Plane': 0.602   # Cargo plane
}

# Country-city structure with coordinates (latitude, longitude)
LOCATIONS = {
    'United Kingdom': {
        'London': (51.5074, -0.1278),
    },
    'France': {
        'Paris': (48.8566, 2.3522),
    },
    'USA': {
        'New York': (40.7128, -74.0060),
    },
    'China': {
        'Shanghai': (31.2304, 121.4737),
    },
    'Japan': {
        'Tokyo': (35.6762, 139.6503),
    },
    'Australia': {
        'Sydney': (-33.8688, 151.2093),
    }
}

# Carbon pricing data (as of April 2025, based on EU ETS)
CARBON_PRICE_EUR_PER_TON = 65.89  # EU ETS price, adjusted from web ID 8
EXCHANGE_RATES = {
    'EUR': 1.0,
    'USD': 1.06,  # Approximate
    'AUD': 1.62,  # Approximate
    'SAR': 3.98   # Approximate
}

# Get coordinates for a city
def get_coordinates(country, city):
    return LOCATIONS.get(country, {}).get(city, (0, 0))

# Calculate distance using Haversine formula
def calculate_distance(country1, city1, country2, city2):
    lat1, lon1 = get_coordinates(country1, city1)
    lat2, lon2 = get_coordinates(country2, city2)
    if lat1 == 0 and lon1 == 0 or lat2 == 0 and lon2 == 0:
        return 500.0  # Default distance if coordinates not found
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return round(R * c, 2)

# Calculate CO₂ emissions
def calculate_co2(country1, city1, country2, city2, transport_mode, distance_km, weight_tons):
    emission_factor = EMISSION_FACTORS.get(transport_mode, 0.096)
    co2_kg = distance_km * weight_tons * emission_factor
    return round(co2_kg, 2)

# Optimize route by combining transport modes for green logistics
def optimize_route(country1, city1, country2, city2, distance_km, weight_tons):
    intercontinental = country1 != country2
    distance_short = distance_km < 1000
    distance_medium = 1000 <= distance_km < 5000
    distance_long = distance_km >= 5000

    combinations = []
    if intercontinental:
        if distance_long:
            combinations.extend([
                ('Ship', 0.9, 'Train', 0.1),
                ('Ship', 0.8, 'Truck', 0.2),
                ('Plane', 0.5, 'Ship', 0.5)
            ])
        elif distance_medium:
            combinations.extend([
                ('Ship', 0.7, 'Train', 0.3),
                ('Plane', 0.4, 'Truck', 0.6),
                ('Ship', 0.6, 'Plane', 0.4)
            ])
        else:
            combinations.extend([
                ('Train', 0.8, 'Truck', 0.2),
                ('Ship', 0.5, 'Truck', 0.5),
                ('Plane', 0.3, 'Truck', 0.7)
            ])
    else:
        if distance_short:
            combinations.extend([
                ('Train', 0.9, 'Truck', 0.1),
                ('Truck', 1.0, None, 0.0),
                ('Train', 1.0, None, 0.0)
            ])
        else:
            combinations.extend([
                ('Train', 0.7, 'Truck', 0.3),
                ('Truck', 0.6, 'Train', 0.4),
                ('Plane', 0.3, 'Truck', 0.7)
            ])

    best_option = None
    min_co2 = float('inf')
    best_breakdown = None
    best_distances = None
    
    for mode1, ratio1, mode2, ratio2 in combinations:
        dist1 = distance_km * ratio1
        dist2 = distance_km * ratio2 if mode2 else 0
        co2_1 = dist1 * weight_tons * EMISSION_FACTORS[mode1]
        co2_2 = dist2 * weight_tons * EMISSION_FACTORS[mode2] if mode2 else 0
        total_co2 = co2_1 + co2_2
        if total_co2 < min_co2:
            min_co2 = total_co2
            best_option = (mode1, ratio1, mode2, ratio2)
            best_breakdown = (co2_1, co2_2)
            best_distances = (dist1, dist2)
    
    return best_option, round(min_co2, 2), best_breakdown, best_distances

# Save emission data to SQLite
def save_emission(source, destination, transport_mode, distance_km, co2_kg, weight_tons):
    with sqlite3.connect('emissions.db') as conn:
        c = conn.cursor()
        emission_id = str(uuid.uuid4())
        c.execute('INSERT INTO emissions (id, source, destination, transport_mode, distance_km, co2_kg, weight_tons) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (emission_id, source, destination, transport_mode, distance_km, co2_kg, weight_tons))
        conn.commit()

# Get all emissions for reporting
def get_emissions():
    with sqlite3.connect('emissions.db') as conn:
        df = pd.read_sql_query('SELECT * FROM emissions', conn)
    return df

# Get suppliers with filters
def get_suppliers(country=None, city=None, material=None):
    with sqlite3.connect('emissions.db') as conn:
        query = 'SELECT * FROM suppliers'
        params = []
        conditions = []
        if country and country != "All":
            conditions.append('country = ?')
            params.append(country)
        if city and city != "All":
            conditions.append('city = ?')
            params.append(city)
        if material:
            conditions.append('LOWER(material) LIKE ?')
            params.append(f'%{material.lower()}%')
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        df = pd.read_sql_query(query, conn, params=params)
    return df

# Streamlit app
def main():
    st.set_page_config(page_title="CO₂ Emission Calculator", layout="wide")
    init_db()

    # Initialize session state for page navigation and sourcing data
    if 'page' not in st.session_state:
        st.session_state.page = "Calculate Emissions"
    if 'source_country' not in st.session_state:
        st.session_state.source_country = list(LOCATIONS.keys())[0]  # Default to first country
    if 'dest_country' not in st.session_state:
        st.session_state.dest_country = list(LOCATIONS.keys())[0]  # Default to first country
    if 'weight_tons' not in st.session_state:
        st.session_state.weight_tons = 1.0

    # Header with company name and navigation
    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
    
    with col1:
        st.markdown(
            """
            <div style='display: flex; align-items: center;'>
                <h1 style='margin: 0; font-size: 28px; color: #2E7D32;'>Carbon 360</h1>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    with col2:
        if st.button("Calculate Emissions", key="nav_calculate"):
            st.session_state.page = "Calculate Emissions"
    
    with col3:
        if st.button("Route Visualizer", key="nav_route"):
            st.session_state.page = "Route Visualizer"
    
    with col4:
        if st.button("Supplier Lookup", key="nav_supplier"):
            st.session_state.page = "Supplier Lookup"
    
    with col5:
        if st.button("Reports", key="nav_reports"):
            st.session_state.page = "Reports"
    
    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)

    # Page content based on selection
    page = st.session_state.page
    
    if page == "Calculate Emissions":
        st.header("Calculate CO₂ Emissions")
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Source")
            source_country = st.selectbox("Source Country", list(LOCATIONS.keys()), 
                                        index=list(LOCATIONS.keys()).index(st.session_state.source_country),
                                        key="source_country_select")
            st.session_state.source_country = source_country
            source_city = st.selectbox("Source City", list(LOCATIONS[source_country].keys()), key="source_city")
            
            st.subheader("Destination")
            dest_country = st.selectbox("Destination Country", list(LOCATIONS.keys()), 
                                      index=list(LOCATIONS.keys()).index(st.session_state.dest_country),
                                      key="dest_country_select")
            st.session_state.dest_country = dest_country
            dest_city = st.selectbox("Destination City", list(LOCATIONS[dest_country].keys()), key="dest_city")
        
        with col2:
            transport_mode = st.selectbox("Transport Mode", list(EMISSION_FACTORS.keys()))
            weight_tons = st.number_input("Weight (tons)", min_value=0.1, value=1.0, step=0.1)
            distance_km = calculate_distance(source_country, source_city, dest_country, dest_city)
            st.write(f"Estimated Distance: {distance_km} km")
        
        if st.button("Calculate"):
            source = f"{source_city}, {source_country}"
            destination = f"{dest_city}, {dest_country}"
            co2_kg = calculate_co2(source_country, source_city, dest_country, dest_city, transport_mode, distance_km, weight_tons)
            st.success(f"Estimated CO₂ Emissions: {co2_kg} kg")
            save_emission(source, destination, transport_mode, distance_km, co2_kg, weight_tons)
            
            # Store source and destination for Supplier Lookup
            st.session_state.source_country = source_country
            st.session_state.dest_country = dest_country
            st.session_state.weight_tons = weight_tons
            
            st.subheader("Calculation Dashboard")
            col3, col4 = st.columns(2)
            with col3:
                st.metric("Total Distance", f"{distance_km} km")
                st.metric("Total CO₂ Emissions", f"{co2_kg} kg")
            with col4:
                st.metric("Emission Factor", f"{EMISSION_FACTORS[transport_mode]} kg CO₂/km/ton")
                st.metric("Weight", f"{weight_tons} tons")
            
            with st.expander("How were these values calculated?"):
                st.write("**Distance Calculation**")
                st.write("The distance between two cities is calculated using the **Haversine Formula**, which computes the great-circle distance between two points on a sphere (Earth).")
                st.write("Formula: `a = sin²(Δlat/2) + cos(lat1) * cos(lat2) * sin²(Δlon/2)`")
                st.write("`c = 2 * atan2(√a, √(1-a))`")
                st.write("`distance = R * c` (where R = 6371 km, Earth's radius)")
                st.write(f"Coordinates used: {source_city} ({get_coordinates(source_country, source_city)}), {dest_city} ({get_coordinates(dest_country, dest_city)})")
                
                st.write("**CO₂ Emission Calculation**")
                st.write("CO₂ emissions are calculated using DEFRA emission factors for each transport mode.")
                st.write("Formula: `CO₂ (kg) = Distance (km) * Weight (tons) * Emission Factor (kg CO₂/km/ton)`")
                st.write(f"Emission Factor for {transport_mode}: {EMISSION_FACTORS[transport_mode]} kg CO₂/km/ton")
                st.write(f"Calculation: {distance_km} km * {weight_tons} tons * {EMISSION_FACTORS[transport_mode]} = {co2_kg} kg")
    
    elif page == "Route Visualizer":
        st.header("Emission Hotspot Visualizer")
        emissions = get_emissions()
        
        if not emissions.empty:
            emissions['source_country'] = emissions['source'].apply(lambda x: x.split(', ')[1])
            emissions['source_city'] = emissions['source'].apply(lambda x: x.split(', ')[0])
            emissions['dest_country'] = emissions['destination'].apply(lambda x: x.split(', ')[1])
            emissions['dest_city'] = emissions['destination'].apply(lambda x: x.split(', ')[0])
            
            valid_coords = []
            for _, row in emissions.iterrows():
                src_coords = get_coordinates(row['source_country'], row['source_city'])
                dst_coords = get_coordinates(row['dest_country'], row['dest_city'])
                if src_coords != (0, 0):
                    valid_coords.append(src_coords)
                if dst_coords != (0, 0):
                    valid_coords.append(dst_coords)
            
            if valid_coords:
                avg_lat = sum(coord[0] for coord in valid_coords) / len(valid_coords)
                avg_lon = sum(coord[1] for coord in valid_coords) / len(valid_coords)
            else:
                avg_lat, avg_lon = 48.8566, 2.3522
            
            m = folium.Map(location=[avg_lat, avg_lon], zoom_start=2, tiles='OpenStreetMap')
            
            for _, row in emissions.iterrows():
                source_coords = get_coordinates(row['source_country'], row['source_city'])
                dest_coords = get_coordinates(row['dest_country'], row['dest_city'])
                if source_coords != (0, 0) and dest_coords != (0, 0):
                    mid_lat = (source_coords[0] + dest_coords[0]) / 2
                    mid_lon = (source_coords[1] + dest_coords[1]) / 2
                    m.location = [mid_lat, mid_lon]
                    
                    color = 'red' if row['co2_kg'] > 1000 else 'orange' if row['co2_kg'] > 500 else 'green'
                    folium.PolyLine(
                        locations=[source_coords, dest_coords],
                        color=color,
                        weight=3,
                        popup=f"{row['source']} to {row['destination']}: {row['co2_kg']} kg"
                    ).add_to(m)
                    folium.Marker(
                        location=source_coords,
                        popup=f"{row['source']}: {row['co2_kg']} kg",
                        icon=folium.Icon(color=color)
                    ).add_to(m)
                    folium.Marker(
                        location=dest_coords,
                        popup=f"{row['destination']}: {row['co2_kg']} kg",
                        icon=folium.Icon(color=color)
                    ).add_to(m)
            
            legend_html = '''
            <div style="position: fixed; bottom: 50px; left: 50px; z-index: 1000; padding: 10px; background-color: white; border: 2px solid black; border-radius: 5px;">
                <p><strong>CO₂ Emission Legend</strong></p>
                <p><span style="color: green;">■</span> Low (<500 kg)</p>
                <p><span style="color: orange;">■</span> Medium (500-1000 kg)</p>
                <p><span style="color: red;">■</span> High (>1000 kg)</p>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(legend_html))
            
            folium_static(m, width=1200, height=600)
            
            st.subheader("Route Analytics Dashboard")
            routes = []
            for idx, row in emissions.iterrows():
                routes.append(f"Route {idx + 1}: {row['source']} to {row['destination']}")
            
            selected_route = st.selectbox("Select Route to Analyze", routes)
            route_idx = int(selected_route.split(":")[0].split(" ")[1]) - 1
            row = emissions.iloc[route_idx]
            
            source_country = row['source_country']
            source_city = row['source_city']
            dest_country = row['dest_country']
            dest_city = row['dest_city']
            distance_km = row['distance_km']
            weight_tons = row['weight_tons']
            current_co2 = row['co2_kg']
            current_mode = row['transport_mode']
            
            best_option, min_co2, breakdown, distances = optimize_route(source_country, source_city, dest_country, dest_city, distance_km, weight_tons)
            mode1, ratio1, mode2, ratio2 = best_option
            co2_1, co2_2 = breakdown
            dist1, dist2 = distances
            savings = current_co2 - min_co2
            
            st.subheader("Key Performance Indicators (KPIs)")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Distance", f"{distance_km:.2f} km")
            with col2:
                st.metric("Current CO₂ Emissions", f"{current_co2:.2f} kg")
            with col3:
                st.metric("Optimized CO₂ Emissions", f"{min_co2:.2f} kg")
            with col4:
                st.metric("CO₂ Savings", f"{savings:.2f} kg ({(savings/current_co2*100):.1f}% reduction)")
            
            tab1, tab2 = st.tabs(["Route Breakdown", "Comparison Chart"])
            
            with tab1:
                st.write("**Optimized Route Breakdown**")
                if mode2:
                    st.write(f"- **{mode1}**: {dist1:.2f} km, CO₂: {co2_1:.2f} kg")
                    st.write(f"- **{mode2}**: {dist2:.2f} km, CO₂: {co2_2:.2f} kg")
                else:
                    st.write(f"- **{mode1}**: {dist1:.2f} km, CO₂: {co2_1:.2f} kg")
            
            with tab2:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[current_co2, min_co2],
                    y=['Old Route', 'New Route'],
                    orientation='h',
                    name='CO₂ Emissions (kg)',
                    marker_color=['#FF4B4B', '#36A2EB']
                ))
                fig.add_trace(go.Bar(
                    x=[distance_km, dist1 if not mode2 else dist1 + dist2],
                    y=['Old Route', 'New Route'],
                    orientation='h',
                    name='Distance (km)',
                    marker_color=['#FF9999', '#66B3FF']
                ))
                fig.update_layout(
                    title="Old Route vs New Route Comparison",
                    barmode='group',
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No emission routes to display. Calculate some emissions first!")
    
    elif page == "Supplier Lookup":
        st.header("Supplier Lookup Dashboard")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            country = st.selectbox("Country", ["All"] + list(LOCATIONS.keys()))
        with col2:
            cities = ["All"] + list(LOCATIONS.get(country, {}).keys()) if country != "All" else ["All"]
            city = st.selectbox("City", cities)
        with col3:
            material = st.text_input("Material (e.g., Steel, Electronics, Textiles, Chemicals)")
        
        suppliers = get_suppliers(country if country != "All" else None, 
                                 city if city != "All" else None, 
                                 material or None)
        
        if not suppliers.empty:
            # KPIs
            st.subheader("Key Performance Indicators (KPIs)")
            col4, col5, col6, col7 = st.columns(4)
            with col4:
                st.metric("Total Suppliers", len(suppliers))
            with col5:
                st.metric("Average Green Score", f"{suppliers['green_score'].mean():.1f}")
            with col6:
                st.metric("Total Capacity", f"{suppliers['annual_capacity_tons'].sum():,} tons")
            
            # Local Sourcing Suggestion
            potential_savings = 0
            if st.session_state.source_country and st.session_state.dest_country:
                source_country = st.session_state.source_country
                dest_country = st.session_state.dest_country
                weight_tons = st.session_state.weight_tons
                distance_km = calculate_distance(source_country, list(LOCATIONS[source_country].keys())[0],
                                               dest_country, list(LOCATIONS[dest_country].keys())[0])
                # Assume Truck for default transport to calculate potential savings
                current_co2 = distance_km * weight_tons * EMISSION_FACTORS['Truck']
                local_suppliers = suppliers[suppliers['country'] == dest_country]
                if not local_suppliers.empty:
                    potential_savings = current_co2  # If sourced locally, shipping emissions are 0
                    st.success(
                        f"🌍 **Local Sourcing Opportunity**: Consider sourcing from {dest_country} to eliminate shipping emissions. "
                        f"There are {len(local_suppliers)} suppliers in {dest_country} that can meet your needs, potentially saving {potential_savings:.2f} kg CO₂."
                    )
                else:
                    st.info(f"No suppliers found in {dest_country}. Consider a dual sourcing strategy by combining local and regional suppliers.")
            with col7:
                st.metric("Potential CO₂ Savings", f"{potential_savings:.2f} kg")
            
            # Interactive Charts
            st.subheader("Supplier Insights 📊")
            tab1, tab2, tab3 = st.tabs(["Supplier Distribution", "Material Availability", "Supplier Details"])
            
            with tab1:
                fig = px.bar(suppliers.groupby('country').size().reset_index(name='Count'),
                            x='country', y='Count', title="Suppliers by Country",
                            labels={'country': 'Country', 'Count': 'Number of Suppliers'})
                st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                fig = px.bar(suppliers.groupby('material')['annual_capacity_tons'].sum().reset_index(),
                            x='material', y='annual_capacity_tons', title="Material Capacity by Type",
                            labels={'material': 'Material', 'annual_capacity_tons': 'Capacity (tons)'})
                st.plotly_chart(fig, use_container_width=True)
            
            with tab3:
                st.dataframe(suppliers[['supplier_name', 'country', 'city', 'material', 'green_score', 'annual_capacity_tons']])
        else:
            st.info("No suppliers found for the given criteria.")
    
    elif page == "Reports":
        st.header("Emission Reports")
        emissions = get_emissions()
        
        if not emissions.empty:
            total_co2 = emissions['co2_kg'].sum()
            avg_co2 = emissions['co2_kg'].mean()
            total_shipments = len(emissions)
            
            total_savings = 0
            route_data = []
            for _, row in emissions.iterrows():
                source_country = row['source'].split(', ')[1]
                source_city = row['source'].split(', ')[0]
                dest_country = row['destination'].split(', ')[1]
                dest_city = row['destination'].split(', ')[0]
                distance_km = row['distance_km']
                weight_tons = row['weight_tons']
                current_co2 = row['co2_kg']
                current_mode = row['transport_mode']
                
                best_option, min_co2, breakdown, distances = optimize_route(source_country, source_city, dest_country, dest_city, distance_km, weight_tons)
                mode1, ratio1, mode2, ratio2 = best_option
                co2_1, co2_2 = breakdown
                dist1, dist2 = distances
                savings = current_co2 - min_co2
                total_savings += savings
                
                route_data.append({
                    'Route': f"{source_city}, {source_country} to {dest_city}, {dest_country}",
                    'Old Mode': current_mode,
                    'Old Distance': distance_km,
                    'Old CO₂': current_co2,
                    'New Modes': f"{mode1} + {mode2 if mode2 else 'None'}",
                    'New Distances': f"{dist1:.2f} km ({mode1}) + {dist2:.2f} km ({mode2 if mode2 else 'N/A'})",
                    'New CO₂': min_co2,
                    'Savings': savings
                })
            
            tab1, tab2, tab3, tab4 = st.tabs(["Summary", "CO₂ Insights", "Route Optimization", "Detailed Data"])
            
            with tab1:
                st.subheader("Summary Statistics")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total CO₂ Emissions", f"{total_co2:.2f} kg")
                with col2:
                    st.metric("Total Shipments", f"{total_shipments}")
                with col3:
                    st.metric("Average CO₂ per Shipment", f"{avg_co2:.2f} kg")
                with col4:
                    st.metric("Total CO₂ Savings", f"{total_savings:.2f} kg")
                
                st.subheader("Emission Breakdown by Transport Mode 📉")
                mode_summary = emissions.groupby('transport_mode')['co2_kg'].sum().reset_index()
                fig = px.pie(mode_summary, values='co2_kg', names='transport_mode', 
                             title="CO₂ Emissions by Transport Mode")
                st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                st.subheader("CO₂ Impact Insights 🌍")
                smartphone_charges = total_co2 * 1000 / 0.008
                ev_distance = total_co2 / 0.2
                st.write(f"**Energy Equivalent** ⚡: The {total_co2:.2f} kg of CO₂ emitted could have been used to:")
                st.write(f"- Charge 📱 {int(smartphone_charges):,} smartphones (assuming 8 g CO₂ per charge).")
                st.write(f"- Power an electric vehicle 🚗 for {ev_distance:.0f} km (assuming 0.2 kg CO₂/km).")
                st.write(f"**Environmental Fact** 🌳: 1 kg of CO₂ is equivalent to the carbon sequestered by 0.05 trees annually.")
                st.write(f"Your emissions could have been offset by planting {int(total_co2 * 0.05):,} trees! 🌲")
            
            with tab3:
                st.subheader("Route Optimization Summary 📊")
                
                currency = st.selectbox("Select Currency for Cost Savings", ['EUR', 'USD', 'AUD', 'SAR'])
                carbon_price_per_kg = (CARBON_PRICE_EUR_PER_TON / 1000) * EXCHANGE_RATES[currency]
                total_cost_savings = total_savings * carbon_price_per_kg
                
                st.write(f"**Carbon Price (April 2025)**: {CARBON_PRICE_EUR_PER_TON:.2f} EUR/tCO₂ (EU ETS)")
                st.write(f"**Converted Price**: {carbon_price_per_kg:.4f} {currency}/kg CO₂")
                st.write(f"**Total Cost Savings**: {total_cost_savings:.2f} {currency} (based on {total_savings:.2f} kg CO₂ saved)")
                
                df_routes = pd.DataFrame(route_data)
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=df_routes['Old CO₂'],
                    y=df_routes['Route'],
                    orientation='h',
                    name='Old Route CO₂ (kg)',
                    marker_color='#FF4B4B'
                ))
                fig.add_trace(go.Bar(
                    x=df_routes['New CO₂'],
                    y=df_routes['Route'],
                    orientation='h',
                    name='New Route CO₂ (kg)',
                    marker_color='#36A2EB'
                ))
                fig.update_layout(
                    title="Old vs New Route CO₂ Emissions",
                    barmode='group',
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
                
                st.dataframe(df_routes[['Route', 'Old Mode', 'Old Distance', 'Old CO₂', 'New Modes', 'New Distances', 'New CO₂', 'Savings']])
            
            with tab4:
                st.subheader("Detailed Data 📋")
                st.dataframe(emissions)
                
                csv = emissions.to_csv(index=False)
                st.download_button(
                    label="Download as CSV",
                    data=csv,
                    file_name="emissions_report.csv",
                    mime="text/csv"
                )
        else:
            st.info("No emission data available. Calculate some emissions first!")

if __name__ == "__main__":
    main()