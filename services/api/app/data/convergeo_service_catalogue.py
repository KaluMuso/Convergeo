"""Convergeo Strategy Brief §5 — Comprehensive Service & Vendor Catalogue (pp.86–94).

Source: docs/concept/Convergeo_Strategy_Bible.pdf
Organised as verticals with sub-categories; archetype + regulator mirror the brief table.
"""

from __future__ import annotations

from typing import Any

# 17 vertical groupings in the brief table (~110 sub-categories total).
CONVERGEO_SERVICE_TAXONOMY: list[dict[str, Any]] = [
    {
        "name": "Beauty & Personal Care",
        "subcategories": [
            {"name": "Hair salons & barbers", "archetype": "Bookable"},
            {"name": "Nail technicians & spas", "archetype": "Bookable"},
            {"name": "Make-up artists", "archetype": "Bookable / Quote"},
            {
                "name": "Massage & wellness therapists",
                "archetype": "Bookable",
                "regulator": "HPCZ if therapeutic",
            },
        ],
    },
    {
        "name": "Health & Medical",
        "subcategories": [
            {
                "name": "General practitioners & clinics",
                "archetype": "Bookable",
                "regulator": "HPCZ",
            },
            {"name": "Dental practices", "archetype": "Bookable", "regulator": "HPCZ"},
            {
                "name": "Optometrists & opticians",
                "archetype": "Bookable / Buy-now",
                "regulator": "HPCZ",
            },
            {
                "name": "Physiotherapy & chiropractic",
                "archetype": "Bookable",
                "regulator": "HPCZ",
            },
            {
                "name": "Diagnostic & imaging labs",
                "archetype": "Bookable",
                "regulator": "HPCZ / ZAMRA",
            },
            {
                "name": "Pharmacies",
                "archetype": "Buy-now / Walk-in",
                "regulator": "ZAMRA",
            },
            {
                "name": "Mental health & counselling",
                "archetype": "Bookable",
                "regulator": "HPCZ",
            },
            {
                "name": "Veterinary clinics",
                "archetype": "Bookable",
                "regulator": "Vet Council of Zambia",
            },
        ],
    },
    {
        "name": "Food & Hospitality",
        "subcategories": [
            {
                "name": "Restaurants & cafes",
                "archetype": "Walk-in / Buy-now",
                "regulator": "Local council, ZABS",
            },
            {
                "name": "Bars & lounges",
                "archetype": "Walk-in",
                "regulator": "Liquor Licensing Board",
            },
            {
                "name": "Catering & event food",
                "archetype": "Quote",
                "regulator": "Local council",
            },
            {
                "name": "Lodges & guesthouses",
                "archetype": "Reservation",
                "regulator": "Tourism Council of Zambia",
            },
            {
                "name": "Hotels",
                "archetype": "Reservation",
                "regulator": "Tourism Council of Zambia",
            },
            {
                "name": "Self-catering apartments",
                "archetype": "Reservation",
                "regulator": "Tourism Council of Zambia",
            },
            {"name": "Conference & event venues", "archetype": "Reservation / Quote"},
            {
                "name": "Bakeries & confectioneries",
                "archetype": "Buy-now / Quote",
                "regulator": "Local council",
            },
        ],
    },
    {
        "name": "Food Retail & Production",
        "subcategories": [
            {
                "name": "Butcheries",
                "archetype": "Buy-now",
                "regulator": "Ministry of Health, ZABS",
            },
            {
                "name": "Fishmongers & fish farms",
                "archetype": "Buy-now / Quote",
                "regulator": "DoF",
            },
            {"name": "Dairies", "archetype": "Buy-now", "regulator": "ZABS"},
            {"name": "Greengrocers & farm-to-table", "archetype": "Buy-now"},
            {"name": "Supermarkets & mini-marts", "archetype": "Buy-now / Walk-in"},
            {
                "name": "Salaula & fresh produce markets",
                "archetype": "Walk-in",
                "regulator": "Local council",
            },
        ],
    },
    {
        "name": "Fitness & Sport",
        "subcategories": [
            {"name": "Gyms & fitness centres", "archetype": "Walk-in / Subscription"},
            {"name": "Swimming pools", "archetype": "Walk-in"},
            {"name": "Yoga & pilates studios", "archetype": "Bookable / Subscription"},
            {
                "name": "Sports clubs (golf, tennis, squash)",
                "archetype": "Reservation / Subscription",
            },
            {"name": "Personal trainers", "archetype": "Bookable"},
            {"name": "Sports academies & coaching", "archetype": "Subscription"},
        ],
    },
    {
        "name": "Automotive & Transport",
        "subcategories": [
            {
                "name": "Mechanics & service centres",
                "archetype": "Bookable / Quote",
                "regulator": "RTSA",
            },
            {"name": "Tyre & battery shops", "archetype": "Buy-now / Walk-in"},
            {"name": "Car wash & detailing", "archetype": "Walk-in / Bookable"},
            {"name": "Auto parts retailers", "archetype": "Buy-now"},
            {
                "name": "Car dealerships (new & used)",
                "archetype": "Quote",
                "regulator": "RTSA",
            },
            {"name": "Car hire", "archetype": "Reservation", "regulator": "RTSA"},
            {
                "name": "Driving schools",
                "archetype": "Bookable / Subscription",
                "regulator": "RTSA",
            },
            {"name": "Logistics & courier", "archetype": "Quote / Buy-now", "regulator": "RTSA"},
            {
                "name": "Boda-boda & motorcycle taxis",
                "archetype": "On-demand",
                "regulator": "RTSA",
            },
        ],
    },
    {
        "name": "Home Services",
        "subcategories": [
            {"name": "Plumbers", "archetype": "Quote / Bookable"},
            {
                "name": "Electricians",
                "archetype": "Quote / Bookable",
                "regulator": "ERB for solar",
            },
            {"name": "Carpenters & joinery", "archetype": "Quote"},
            {"name": "Painters & decorators", "archetype": "Quote"},
            {"name": "Cleaning services", "archetype": "Bookable / Subscription"},
            {"name": "Pest control", "archetype": "Bookable", "regulator": "ZEMA"},
            {"name": "Solar installers", "archetype": "Quote", "regulator": "ERB"},
            {"name": "Borehole drilling & water", "archetype": "Quote", "regulator": "WARMA"},
            {"name": "Landscaping & gardening", "archetype": "Bookable / Subscription"},
            {
                "name": "Security & CCTV installation",
                "archetype": "Quote",
                "regulator": "PSIRA-type registration",
            },
        ],
    },
    {
        "name": "Construction & Real Estate",
        "subcategories": [
            {
                "name": "Building contractors",
                "archetype": "Quote",
                "regulator": "NCC",
            },
            {"name": "Architects", "archetype": "Quote", "regulator": "ZIA"},
            {
                "name": "Quantity surveyors & engineers",
                "archetype": "Quote",
                "regulator": "EIZ / SIZ",
            },
            {"name": "Hardware & building supplies", "archetype": "Buy-now"},
            {
                "name": "Real estate agents",
                "archetype": "Listing-based",
                "regulator": "ZIEA",
            },
            {
                "name": "Property management",
                "archetype": "Subscription / Quote",
                "regulator": "ZIEA",
            },
            {"name": "Interior designers", "archetype": "Quote"},
        ],
    },
    {
        "name": "Education & Training",
        "subcategories": [
            {
                "name": "Schools (public & private)",
                "archetype": "Subscription",
                "regulator": "Ministry of Education",
            },
            {
                "name": "Colleges & universities",
                "archetype": "Subscription",
                "regulator": "HEA / TEVETA",
            },
            {"name": "Tutoring & exam prep", "archetype": "Bookable"},
            {
                "name": "Skills & vocational training",
                "archetype": "Subscription",
                "regulator": "TEVETA",
            },
            {"name": "Music & arts lessons", "archetype": "Bookable"},
            {"name": "Language schools", "archetype": "Subscription"},
            {"name": "Online courses & coaching", "archetype": "Subscription / Buy-now"},
        ],
    },
    {
        "name": "Professional Services",
        "subcategories": [
            {
                "name": "Lawyers & legal services",
                "archetype": "Bookable / Quote",
                "regulator": "LAZ",
            },
            {
                "name": "Accountants & tax consultants",
                "archetype": "Bookable / Quote",
                "regulator": "ZICA",
            },
            {
                "name": "Business registration & PACRA agents",
                "archetype": "Quote",
                "regulator": "PACRA",
            },
            {"name": "Insurance brokers", "archetype": "Quote", "regulator": "PIA"},
            {"name": "Marketing & PR agencies", "archetype": "Quote"},
            {"name": "Translation & interpretation", "archetype": "Quote"},
            {"name": "Recruitment & staffing", "archetype": "Quote"},
            {
                "name": "Notary & document services",
                "archetype": "Bookable",
                "regulator": "LAZ",
            },
        ],
    },
    {
        "name": "Creative & Media",
        "subcategories": [
            {"name": "Photographers & videographers", "archetype": "Bookable / Quote"},
            {"name": "Graphic designers", "archetype": "Quote"},
            {"name": "Web & app developers", "archetype": "Quote"},
            {"name": "Printing shops", "archetype": "Quote / Buy-now"},
            {"name": "Sign-writing & branding", "archetype": "Quote"},
            {"name": "DJs & musicians", "archetype": "Bookable"},
            {"name": "MCs & event hosts", "archetype": "Bookable"},
            {"name": "Event planners & decorators", "archetype": "Quote"},
        ],
    },
    {
        "name": "Agriculture",
        "subcategories": [
            {
                "name": "Agro-dealers (seeds, fertiliser)",
                "archetype": "Buy-now",
                "regulator": "ZARI / Ministry of Agriculture",
            },
            {
                "name": "Veterinary supplies",
                "archetype": "Buy-now",
                "regulator": "Vet Council",
            },
            {"name": "Farm equipment & tractors", "archetype": "Quote / Buy-now"},
            {"name": "Poultry & livestock suppliers", "archetype": "Buy-now / Quote"},
            {
                "name": "Irrigation & farm services",
                "archetype": "Quote",
                "regulator": "WARMA",
            },
            {"name": "Agronomy & extension services", "archetype": "Bookable / Quote"},
        ],
    },
    {
        "name": "Crafts & Manufacturing",
        "subcategories": [
            {"name": "Tailors & dressmakers", "archetype": "Quote / Bookable"},
            {"name": "Leather workers & cobblers", "archetype": "Buy-now / Quote"},
            {"name": "Curio & art galleries", "archetype": "Buy-now"},
            {"name": "Furniture makers", "archetype": "Quote / Buy-now"},
            {"name": "Welders & metal fabricators", "archetype": "Quote"},
            {"name": "Pottery, basketry, beadwork", "archetype": "Buy-now"},
        ],
    },
    {
        "name": "Financial & Digital",
        "subcategories": [
            {
                "name": "Mobile money agents",
                "archetype": "Walk-in",
                "regulator": "BoZ",
            },
            {"name": "Microfinance & lending", "archetype": "Quote", "regulator": "BoZ"},
            {"name": "Forex bureaux", "archetype": "Walk-in", "regulator": "BoZ"},
            {"name": "Insurance providers", "archetype": "Quote", "regulator": "PIA"},
            {"name": "IT support & repair", "archetype": "Bookable / Quote"},
            {
                "name": "Internet service providers",
                "archetype": "Subscription",
                "regulator": "ZICTA",
            },
            {"name": "Cyber cafes & print bureaus", "archetype": "Walk-in"},
        ],
    },
    {
        "name": "Tourism & Leisure",
        "subcategories": [
            {
                "name": "Tour operators",
                "archetype": "Reservation / Quote",
                "regulator": "Tourism Council of Zambia",
            },
            {
                "name": "Tour guides (independent)",
                "archetype": "Bookable",
                "regulator": "Tourism Council of Zambia",
            },
            {
                "name": "Adventure activities",
                "archetype": "Bookable",
                "regulator": "Tourism Council of Zambia",
            },
            {"name": "Cinemas & entertainment venues", "archetype": "Buy-now"},
            {"name": "Game parks & reserves", "archetype": "Reservation", "regulator": "DNPW"},
            {
                "name": "Boat hire & water sports",
                "archetype": "Reservation",
                "regulator": "Department of Maritime",
            },
        ],
    },
    {
        "name": "Events",
        "subcategories": [
            {"name": "Concerts & festivals", "archetype": "Event ticket"},
            {"name": "Conferences & expos", "archetype": "Event ticket"},
            {"name": "Sports events & fixtures", "archetype": "Event ticket"},
            {"name": "Workshops & masterclasses", "archetype": "Event ticket"},
            {"name": "Religious & community events", "archetype": "Event ticket / Free RSVP"},
        ],
    },
    {
        "name": "Public & Misc",
        "subcategories": [
            {"name": "Funeral services", "archetype": "Quote"},
            {"name": "Religious institutions", "archetype": "Listing-based"},
            {
                "name": "Animal services & boarding",
                "archetype": "Bookable",
                "regulator": "Vet Council",
            },
            {"name": "Childcare & nannies", "archetype": "Bookable / Quote"},
            {"name": "Elder care", "archetype": "Bookable / Quote"},
            {"name": "Errand & concierge services", "archetype": "Bookable"},
        ],
    },
]
