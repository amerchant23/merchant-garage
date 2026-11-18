
import json
import urllib.parse
import urllib.request

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Merchant Garage",
    page_icon="🚗",
    layout="wide"
)


# ============================================================
# CONFIGURATION
# ============================================================

APP_DIR = Path(__file__).parent

SERVICE_INTERVALS = {
    "Oil change": 5000,
    "Tire rotation": 6000,
    "Engine air filter": 15000,
    "Cabin air filter": 15000,
    "Coolant": 50000,
    "Transmission service": 60000,
}

SERVICE_CATEGORIES = [
    "Oil change",
    "Tire rotation",
    "Engine air filter",
    "Cabin air filter",
    "Brakes",
    "Coolant",
    "Transmission service",
    "Battery",
    "Inspection",
    "Other",
]


# ============================================================
# SUPABASE CONNECTION
# ============================================================

@st.cache_resource
def get_supabase_client():

    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]

    return create_client(url, key)


supabase = get_supabase_client()


# ============================================================
# VEHICLE FUNCTIONS
# ============================================================

def load_vehicles():

    result = (
        supabase.table("vehicles")
        .select("*")
        .order("id", desc=True)
        .execute()
    )

    return result.data or []


def add_vehicle(name, year, make, model, mileage, vin):

    display_name = name.strip() or " ".join(
        part
        for part in [
            year.strip(),
            make.strip(),
            model.strip()
        ]
        if part
    )

    supabase.table("vehicles").insert({
        "name": display_name,
        "year": year.strip(),
        "make": make.strip(),
        "model": model.strip(),
        "current_mileage": mileage,
        "vin": vin.strip()
    }).execute()


# ============================================================
# SERVICE HISTORY FUNCTIONS
# ============================================================

def load_history(vehicle_id):

    result = (
        supabase.table("service_records")
        .select("*")
        .eq("vehicle_id", vehicle_id)
        .order("service_date", desc=True)
        .order("id", desc=True)
        .execute()
    )

    return result.data or []


def money(value):

    return f"${float(value or 0):,.2f}"


def add_service(
    vehicle_id,
    category,
    service_date,
    mileage,
    cost,
    shop,
    notes,
    next_due_mileage,
    next_due_date
):

    supabase.table("service_records").insert({

        "vehicle_id": vehicle_id,
        "category": category,
        "service_date": service_date.isoformat(),
        "mileage": mileage,
        "cost": cost,
        "shop": shop.strip(),
        "notes": notes.strip(),
        "next_due_mileage": next_due_mileage,
        "next_due_date": (
            next_due_date.isoformat()
            if next_due_date else None
        )

    }).execute()

    vehicle_result = (
        supabase.table("vehicles")
        .select("current_mileage")
        .eq("id", vehicle_id)
        .single()
        .execute()
    )

    current_mileage = vehicle_result.data["current_mileage"]

    if mileage > current_mileage:

        supabase.table("vehicles").update({
            "current_mileage": mileage
        }).eq("id", vehicle_id).execute()


def delete_service(record_id):

    (
        supabase.table("service_records")
        .delete()
        .eq("id", record_id)
        .execute()
    )


# ============================================================
# MILEAGE TRACKING FUNCTIONS
# ============================================================

def load_mileage_history(vehicle_id):

    result = (
        supabase.table("mileage_readings")
        .select("*")
        .eq("vehicle_id", vehicle_id)
        .order("reading_date", desc=True)
        .order("id", desc=True)
        .execute()
    )

    return result.data or []


def add_mileage_reading(vehicle_id, mileage, reading_date):

    vehicle_result = (
        supabase.table("vehicles")
        .select("current_mileage")
        .eq("id", vehicle_id)
        .single()
        .execute()
    )

    if not vehicle_result.data:

        raise ValueError("Vehicle not found.")

    current_mileage = vehicle_result.data["current_mileage"]

    if mileage < current_mileage:

        raise ValueError(
            "Mileage cannot be lower than the previously "
            "recorded odometer reading."
        )

    supabase.table("mileage_readings").insert({

        "vehicle_id": vehicle_id,
        "reading_date": reading_date.isoformat(),
        "mileage": mileage

    }).execute()

    supabase.table("vehicles").update({

        "current_mileage": mileage

    }).eq("id", vehicle_id).execute()


# ============================================================
# APP SETTINGS FUNCTIONS
# ============================================================

def get_setting(key, default=None):

    result = (
        supabase.table("app_settings")
        .select("setting_value")
        .eq("setting_key", key)
        .limit(1)
        .execute()
    )

    if result.data:

        return result.data[0]["setting_value"]

    return default


# ============================================================
# AUTOMATIC VEHICLE IMAGES
# ============================================================

@st.cache_data(ttl=86400)
def find_vehicle_image(year, make, model):

    search_query = f"{year} {make} {model} car"

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": search_query,
        "gsrnamespace": 6,
        "gsrlimit": 10,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1000,
        "format": "json",
    }

    url = (
        "https://commons.wikimedia.org/w/api.php?"
        + urllib.parse.urlencode(params)
    )

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "MerchantGarage/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=10
        ) as response:

            data = json.loads(
                response.read().decode("utf-8")
            )

        pages = (
            data.get("query", {})
            .get("pages", {})
        )

        if not pages:
            return None

        for page in pages.values():

            image_info = page.get("imageinfo", [])

            if image_info:

                info = image_info[0]
                metadata = info.get("extmetadata", {})

                return {
                    "url": info.get(
                        "thumburl",
                        info.get("url")
                    ),

                    "page": info.get(
                        "descriptionurl",
                        ""
                    ),

                    "title": page.get("title", ""),

                    "license": metadata.get(
                        "LicenseShortName", {}
                    ).get(
                        "value",
                        "See image source"
                    ),
                }

    except Exception:
        return None

    return None


# ============================================================
# SMART GARAGE FUNCTIONS
# ============================================================

def get_monthly_checkin_status(vehicle_id):

    readings = load_mileage_history(vehicle_id)

    if not readings:
        return True

    latest_date = date.fromisoformat(
        readings[0]["reading_date"]
    )

    today = date.today()

    return (
        latest_date.year,
        latest_date.month
    ) < (
        today.year,
        today.month
    )


def upcoming_items(records, current_mileage):

    items = []

    for record in records:

        due_miles = record["next_due_mileage"]
        due_date = record["next_due_date"]

        overdue = False
        details = []

        if due_miles is not None:

            details.append(
                f"Due at {int(due_miles):,} miles"
            )

            overdue = (
                overdue
                or current_mileage >= int(due_miles)
            )

        if due_date:

            parsed_date = date.fromisoformat(due_date)

            details.append(
                f"Due {parsed_date.strftime('%b %d, %Y')}"
            )

            overdue = (
                overdue
                or date.today() >= parsed_date
            )

        if details:

            items.append({

                "category": record["category"],
                "details": " · ".join(details),
                "overdue": overdue,

                "sort_mileage": (
                    due_miles
                    if due_miles is not None
                    else 10**15
                ),

            })

    return sorted(
        items,
        key=lambda item: item["sort_mileage"]
    )


# ============================================================
# CUSTOM STYLING
# ============================================================

st.markdown(
    """
    <style>

        .stApp {
            background-color: #F5F7F7;
            color: #000000;
        }

        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1250px;
        }

        h1 {
            color: #C62828 !important;
            font-weight: 700 !important;
            letter-spacing: -1px;
        }

        h2, h3 {
            color: #000000 !important;
            font-weight: 650 !important;
        }

        .stApp p,
        .stApp label,
        .stApp li {
            color: #000000;
        }

        [data-testid="stMetric"] {
            background-color: #FFFFFF;
            border: 1px solid #E4E9E9;
            padding: 20px;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(23, 43, 61, 0.04);
        }

        [data-testid="stMetricLabel"] {
            color: #000000 !important;
        }

        [data-testid="stMetricValue"] {
            color: #000000 !important;
            font-weight: 700 !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 12px;
            border-bottom: 1px solid #DDE4E5;
        }

        .stTabs [data-baseweb="tab"] {
            color: #000000;
            font-weight: 600;
            padding: 12px 16px;
        }

        .stTabs [aria-selected="true"] {
            color: #C62828 !important;
            border-bottom-color: #C62828 !important;
        }

        .stButton > button,
        .stFormSubmitButton > button {
            background-color: #243C4F;
            color: #FFFFFF !important;
            border: none;
            border-radius: 9px;
            font-weight: 600;
            padding: 9px 18px;
        }

        .stButton > button *,
        .stFormSubmitButton > button * {
            color: #FFFFFF !important;
        }

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            background-color: #405D70;
            color: #FFFFFF !important;
            border: none;
        }

        [data-testid="stAlert"] {
            background-color: #243C4F;
            color: #FFFFFF !important;
        }

        [data-testid="stAlert"] *,
        [data-testid="stAlert"] p {
            color: #FFFFFF !important;
        }

        div[data-baseweb="input"] input,
        div[data-baseweb="select"] {
            border-radius: 8px;
        }

        [data-testid="stSidebar"] {
            background-color: #EDF1F1;
        }

        hr {
            border-color: #E0E6E6;
        }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# APP HEADER
# ============================================================

st.title("🚗 Merchant Garage")

st.caption(
    "A simple place to track your vehicles, "
    "maintenance, and service history."
)


# ============================================================
# VEHICLE SELECTION
# ============================================================

vehicles = load_vehicles()

with st.sidebar:

    st.header("My Vehicles")

    if vehicles:

        vehicle_options = {
            (
                f'{v["name"]} · '
                f'{v["current_mileage"]:,} mi'
            ): v["id"]
            for v in vehicles
        }

        selected_label = st.selectbox(
            "Select a vehicle",
            list(vehicle_options.keys())
        )

        selected_vehicle_id = vehicle_options[
            selected_label
        ]

        selected_vehicle = next(
            v for v in vehicles
            if v["id"] == selected_vehicle_id
        )

    else:

        selected_vehicle = None
        selected_vehicle_id = None

        st.info(
            "Add your first vehicle to get started."
        )

    st.divider()

    st.caption(
        "Your garage is connected to cloud storage."
    )


# ============================================================
# APP TABS
# ============================================================

(
    tab_overview,
    tab_add_vehicle,
    tab_log_service,
    tab_smart,
    tab_history
) = st.tabs([
    "Overview",
    "Add Vehicle",
    "Log Service",
    "Smart Garage",
    "Service History",
])


# ============================================================
# SMART GARAGE TAB
# ============================================================

with tab_smart:

    st.subheader("Smart Garage")

    st.caption(
        "Keep your maintenance schedule up to date "
        "by recording your mileage once a month."
    )

    if not selected_vehicle:

        st.info(
            "Add a vehicle to start using Smart Garage."
        )

    else:

        current_mileage = int(
            selected_vehicle["current_mileage"]
        )

        mileage_history = load_mileage_history(
            selected_vehicle_id
        )

        checkin_due = get_monthly_checkin_status(
            selected_vehicle_id
        )

        st.markdown(
            f"### {selected_vehicle['name']}"
        )

        metric1, metric2 = st.columns(2)

        metric1.metric(
            "Current mileage",
            f"{current_mileage:,} mi"
        )

        metric2.metric(
            "Monthly check-in",
            "Due" if checkin_due else "Completed"
        )

        st.divider()

        if checkin_due:

            st.warning(
                "Your monthly mileage check-in is due! "
                "Enter your current odometer reading below."
            )

        else:

            st.success(
                "Your mileage is up to date for this month!"
            )

        st.markdown("### Update your mileage")

        with st.form(
            f"monthly_mileage_form_{selected_vehicle_id}"
        ):

            new_mileage = st.number_input(
                "Current odometer reading",
                min_value=0,
                value=current_mileage,
                step=100,
                help=(
                    "Enter the mileage currently "
                    "displayed on your dashboard."
                )
            )

            reading_date = st.date_input(
                "Reading date",
                value=date.today(),
                max_value=date.today()
            )

            submitted = st.form_submit_button(
                "Save mileage update",
                type="primary",
                use_container_width=True
            )

            if submitted:

                try:

                    add_mileage_reading(
                        selected_vehicle_id,
                        int(new_mileage),
                        reading_date
                    )

                    st.success(
                        "Mileage updated successfully!"
                    )

                    st.rerun()

                except ValueError as error:

                    st.error(str(error))

        st.divider()

        st.markdown("### Mileage history")

        if not mileage_history:

            st.info(
                "Your monthly mileage history will appear "
                "here after your first update."
            )

        else:

            mileage_rows = []

            for reading in mileage_history:

                mileage_rows.append({

                    "Date": date.fromisoformat(
                        reading["reading_date"]
                    ).strftime("%b %d, %Y"),

                    "Odometer": (
                        f'{reading["mileage"]:,} mi'
                    )

                })

            st.dataframe(
                pd.DataFrame(mileage_rows),
                use_container_width=True,
                hide_index=True
            )

            if len(mileage_history) >= 2:

                latest = mileage_history[0]
                previous = mileage_history[1]

                miles_driven = (
                    int(latest["mileage"])
                    - int(previous["mileage"])
                )

                st.metric(
                    "Miles driven since previous update",
                    f"{miles_driven:,} mi"
                )


# ============================================================
# ADD VEHICLE TAB
# ============================================================

with tab_add_vehicle:

    st.subheader("Add a vehicle")

    with st.form(
        "add_vehicle_form",
        clear_on_submit=True
    ):

        col1, col2 = st.columns(2)

        with col1:

            nickname = st.text_input(
                "Nickname",
                placeholder="e.g. Family SUV"
            )

            year = st.text_input(
                "Year",
                placeholder="e.g. 2022"
            )

            make = st.text_input(
                "Make",
                placeholder="e.g. Toyota"
            )

        with col2:

            model = st.text_input(
                "Model",
                placeholder="e.g. RAV4"
            )

            mileage = st.number_input(
                "Current mileage",
                min_value=0,
                step=100
            )

            vin = st.text_input(
                "VIN (optional)"
            )

        submitted = st.form_submit_button(
            "Save vehicle",
            type="primary"
        )

        if submitted:

            if not make.strip() or not model.strip():

                st.error(
                    "Please enter both the vehicle make and model."
                )

            else:

                add_vehicle(
                    nickname,
                    year,
                    make,
                    model,
                    int(mileage),
                    vin
                )

                st.success("Vehicle added!")

                st.rerun()


# ============================================================
# OVERVIEW TAB - MODERN DASHBOARD
# ============================================================

with tab_overview:

    if selected_vehicle:

        history = load_history(selected_vehicle_id)

        total_spent = sum(
            float(record["cost"] or 0)
            for record in history
        )

        current_mileage = int(
            selected_vehicle["current_mileage"]
        )

        display_vehicle = " ".join(
            part
            for part in [
                selected_vehicle["year"],
                selected_vehicle["make"],
                selected_vehicle["model"],
            ]
            if part
        )

        due = upcoming_items(
            history,
            current_mileage
        )

        overdue_count = sum(
            1 for item in due if item["overdue"]
        )

        upcoming_count = len(due) - overdue_count

        st.markdown("## Your Vehicle")

        photo_col, details_col = st.columns(
            [1.2, 1],
            gap="large"
        )

        with photo_col:

            vehicle_image = find_vehicle_image(
                selected_vehicle["year"],
                selected_vehicle["make"],
                selected_vehicle["model"]
            )

            if vehicle_image and vehicle_image["url"]:

                st.image(
                    vehicle_image["url"],
                    use_container_width=True
                )

                if vehicle_image["page"]:

                    st.caption(
                        f'Image source: '
                        f'[{vehicle_image["title"]}]'
                        f'({vehicle_image["page"]})'
                    )

            else:

                st.info(
                    "Vehicle image unavailable. "
                    "Your vehicle details are still saved."
                )

        with details_col:

            st.markdown(
                f"### {selected_vehicle['name']}"
            )

            st.markdown(
                f"**{display_vehicle}**"
            )

            st.caption("CURRENT ODOMETER")

            st.markdown(
                f"""
                <div style="
                    font-size: 38px;
                    font-weight: 700;
                    color: #243C4F;
                    margin-bottom: 12px;
                ">
                    {current_mileage:,}
                    <span style="
                        font-size: 16px;
                        font-weight: 500;
                    ">miles</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.divider()

            st.markdown("**Maintenance overview**")

            if overdue_count > 0:

                st.error(
                    f"{overdue_count} maintenance item(s) overdue"
                )

            elif upcoming_count > 0:

                st.info(
                    f"{upcoming_count} upcoming maintenance item(s)"
                )

            else:

                st.success(
                    "No outstanding maintenance reminders"
                )

        st.markdown("### At a glance")

        metric1, metric2, metric3 = st.columns(3)

        metric1.metric(
            "Services logged",
            len(history)
        )

        metric2.metric(
            "Total spent",
            money(total_spent)
        )

        metric3.metric(
            "Upcoming items",
            len(due)
        )

        st.divider()

        left, right = st.columns(
            [1, 1],
            gap="large"
        )

        with left:

            st.markdown("### Maintenance")

            if not due:

                st.success(
                    "You're all caught up! "
                    "No maintenance reminders have been added yet."
                )

            else:

                for item in due:

                    if item["overdue"]:

                        st.error(
                            f'**{item["category"]}** · Overdue'
                        )

                    else:

                        st.info(
                            f'**{item["category"]}** · Upcoming'
                        )

                    st.caption(item["details"])

        with right:

            st.markdown("### Recent activity")

            if not history:

                st.info(
                    "Your recent service records will appear here."
                )

            else:

                for record in history[:5]:

                    service_day = date.fromisoformat(
                        record["service_date"]
                    ).strftime("%b %d, %Y")

                    st.markdown(
                        f'**{record["category"]}**'
                    )

                    st.caption(
                        f'{service_day} · '
                        f'{record["mileage"]:,} mi · '
                        f'{money(record["cost"])}'
                    )

                    if record["shop"]:

                        st.caption(
                            f'Service provider: {record["shop"]}'
                        )

                    st.divider()

    else:

        st.info(
            "Welcome to Merchant Garage! "
            "Open the Add Vehicle tab to get started."
        )


# ============================================================
# LOG SERVICE TAB
# ============================================================

with tab_log_service:

    st.subheader("Log a service")

    if not selected_vehicle:

        st.info(
            "Add a vehicle before logging a service."
        )

    else:

        st.caption(
            f'Adding a service for **{selected_vehicle["name"]}**'
        )

        with st.form(
            "add_service_form",
            clear_on_submit=True
        ):

            category = st.selectbox(
                "Service",
                SERVICE_CATEGORIES
            )

            service_date = st.date_input(
                "Date",
                value=date.today()
            )

            mileage_value = st.number_input(
                "Odometer mileage",
                min_value=0,
                value=int(
                    selected_vehicle["current_mileage"]
                ),
                step=100,
            )

            cost = st.number_input(
                "Cost ($)",
                min_value=0.0,
                value=0.0,
                step=5.0
            )

            shop = st.text_input(
                "Shop / provider"
            )

            notes = st.text_area(
                "Notes"
            )

            st.markdown(
                "**Next service reminder (optional)**"
            )

            suggested_interval = SERVICE_INTERVALS.get(
                category
            )

            suggested_mileage = (
                int(mileage_value) + suggested_interval
                if suggested_interval
                else None
            )

            use_suggested = False

            if suggested_interval:

                use_suggested = st.checkbox(
                    (
                        "Use suggested interval "
                        f"(+{suggested_interval:,} miles)"
                    ),
                    value=False,
                )

            next_mileage_text = st.text_input(
                "Next due mileage",
                value=(
                    str(suggested_mileage)
                    if use_suggested and suggested_mileage
                    else ""
                ),
                placeholder="Leave blank if not applicable",
            )

            use_due_date = st.checkbox(
                "Set a calendar due date"
            )

            next_due_date = None

            if use_due_date:

                next_due_date = st.date_input(
                    "Next due date",
                    value=date.today().replace(
                        year=date.today().year + 1
                    ),
                )

            submitted = st.form_submit_button(
                "Save service",
                type="primary"
            )

            if submitted:

                try:

                    next_due_mileage = (
                        int(next_mileage_text.strip())
                        if next_mileage_text.strip()
                        else None
                    )

                    add_service(
                        selected_vehicle_id,
                        category,
                        service_date,
                        int(mileage_value),
                        float(cost),
                        shop,
                        notes,
                        next_due_mileage,
                        next_due_date,
                    )

                    st.success("Service saved!")

                    st.rerun()

                except ValueError:

                    st.error(
                        "Please enter a valid whole number "
                        "for the next due mileage."
                    )


# ============================================================
# SERVICE HISTORY TAB
# ============================================================

with tab_history:

    st.subheader("Service history")

    if not selected_vehicle:

        st.info(
            "Add a vehicle to view its service history."
        )

    else:

        history = load_history(selected_vehicle_id)

        if not history:

            st.info(
                "No service records yet."
            )

        else:

            rows = []

            for record in history:

                rows.append({

                    "Date": date.fromisoformat(
                        record["service_date"]
                    ).strftime("%b %d, %Y"),

                    "Service": record["category"],

                    "Mileage": (
                        f'{record["mileage"]:,}'
                    ),

                    "Cost": money(record["cost"]),

                    "Shop": record["shop"],

                    "Notes": record["notes"],

                })

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True
            )

            st.markdown(
                "**Delete a service record**"
            )

            record_choices = {
                (
                    f'{r["category"]} · '
                    f'{r["service_date"]} · '
                    f'{r["mileage"]:,} mi'
                ): r["id"]
                for r in history
            }

            selected_record = st.selectbox(
                "Choose a record",
                list(record_choices.keys())
            )

            if st.button(
                "Delete selected record",
                type="secondary"
            ):

                delete_service(
                    record_choices[selected_record]
                )

                st.success(
                    "Service record deleted."
                )

                st.rerun()
