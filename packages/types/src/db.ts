export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[];

export type Database = {
  graphql_public: {
    Tables: {
      [_ in never]: never;
    };
    Views: {
      [_ in never]: never;
    };
    Functions: {
      graphql: {
        Args: {
          extensions?: Json;
          operationName?: string;
          query?: string;
          variables?: Json;
        };
        Returns: Json;
      };
    };
    Enums: {
      [_ in never]: never;
    };
    CompositeTypes: {
      [_ in never]: never;
    };
  };
  public: {
    Tables: {
      kyc_records: {
        Row: {
          created_at: string;
          doc_storage_paths: string[];
          id: string;
          momo_name_match: Json | null;
          reviewer_notes: string | null;
          status: string;
          tier: number;
          updated_at: string;
          vendor_id: string;
        };
        Insert: {
          created_at?: string;
          doc_storage_paths?: string[];
          id?: string;
          momo_name_match?: Json | null;
          reviewer_notes?: string | null;
          status?: string;
          tier: number;
          updated_at?: string;
          vendor_id: string;
        };
        Update: {
          created_at?: string;
          doc_storage_paths?: string[];
          id?: string;
          momo_name_match?: Json | null;
          reviewer_notes?: string | null;
          status?: string;
          tier?: number;
          updated_at?: string;
          vendor_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "kyc_records_vendor_id_fkey";
            columns: ["vendor_id"];
            isOneToOne: false;
            referencedRelation: "vendors";
            referencedColumns: ["id"];
          },
        ];
      };
      listing_images: {
        Row: {
          cloudinary_public_id: string;
          created_at: string;
          id: string;
          listing_id: string;
          position: number;
          updated_at: string;
        };
        Insert: {
          cloudinary_public_id: string;
          created_at?: string;
          id?: string;
          listing_id: string;
          position: number;
          updated_at?: string;
        };
        Update: {
          cloudinary_public_id?: string;
          created_at?: string;
          id?: string;
          listing_id?: string;
          position?: number;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "listing_images_listing_id_fkey";
            columns: ["listing_id"];
            isOneToOne: false;
            referencedRelation: "vendor_listings";
            referencedColumns: ["id"];
          },
        ];
      };
      profiles: {
        Row: {
          created_at: string;
          deleted_at: string | null;
          display_name: string | null;
          dpa_consent_at: string | null;
          id: string;
          locale: string;
          notif_prefs: Json;
          phone: string | null;
          updated_at: string;
        };
        Insert: {
          created_at?: string;
          deleted_at?: string | null;
          display_name?: string | null;
          dpa_consent_at?: string | null;
          id: string;
          locale?: string;
          notif_prefs?: Json;
          phone?: string | null;
          updated_at?: string;
        };
        Update: {
          created_at?: string;
          deleted_at?: string | null;
          display_name?: string | null;
          dpa_consent_at?: string | null;
          id?: string;
          locale?: string;
          notif_prefs?: Json;
          phone?: string | null;
          updated_at?: string;
        };
        Relationships: [];
      };
      user_roles: {
        Row: {
          created_at: string;
          id: string;
          role: string;
          updated_at: string;
          user_id: string;
        };
        Insert: {
          created_at?: string;
          id?: string;
          role: string;
          updated_at?: string;
          user_id: string;
        };
        Update: {
          created_at?: string;
          id?: string;
          role?: string;
          updated_at?: string;
          user_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "user_roles_user_id_fkey";
            columns: ["user_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      vendor_locations: {
        Row: {
          created_at: string;
          hours: Json;
          id: string;
          landmark: string;
          lat: number;
          lng: number;
          updated_at: string;
          vendor_id: string;
        };
        Insert: {
          created_at?: string;
          hours?: Json;
          id?: string;
          landmark: string;
          lat: number;
          lng: number;
          updated_at?: string;
          vendor_id: string;
        };
        Update: {
          created_at?: string;
          hours?: Json;
          id?: string;
          landmark?: string;
          lat?: number;
          lng?: number;
          updated_at?: string;
          vendor_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "vendor_locations_vendor_id_fkey";
            columns: ["vendor_id"];
            isOneToOne: false;
            referencedRelation: "vendors";
            referencedColumns: ["id"];
          },
        ];
      };
      vendor_listings: {
        Row: {
          condition: string;
          created_at: string;
          id: string;
          moq: number;
          price_ngwee: number;
          price_tiers: Json | null;
          product_id: string | null;
          return_window_hours: number | null;
          returnable: boolean;
          status: string;
          stock_mode: string;
          stock_qty: number | null;
          title_override: string | null;
          updated_at: string;
          vendor_id: string;
          wholesale: boolean;
        };
        Insert: {
          condition: string;
          created_at?: string;
          id?: string;
          moq?: number;
          price_ngwee: number;
          price_tiers?: Json | null;
          product_id?: string | null;
          return_window_hours?: number | null;
          returnable?: boolean;
          status?: string;
          stock_mode: string;
          stock_qty?: number | null;
          title_override?: string | null;
          updated_at?: string;
          vendor_id: string;
          wholesale?: boolean;
        };
        Update: {
          condition?: string;
          created_at?: string;
          id?: string;
          moq?: number;
          price_ngwee?: number;
          price_tiers?: Json | null;
          product_id?: string | null;
          return_window_hours?: number | null;
          returnable?: boolean;
          status?: string;
          stock_mode?: string;
          stock_qty?: number | null;
          title_override?: string | null;
          updated_at?: string;
          vendor_id?: string;
          wholesale?: boolean;
        };
        Relationships: [
          {
            foreignKeyName: "vendor_listings_product_id_fkey";
            columns: ["product_id"];
            isOneToOne: false;
            referencedRelation: "products";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "vendor_listings_vendor_id_fkey";
            columns: ["vendor_id"];
            isOneToOne: false;
            referencedRelation: "vendors";
            referencedColumns: ["id"];
          },
        ];
      };
      vendors: {
        Row: {
          caps_snapshot: Json;
          created_at: string;
          description: string | null;
          display_name: string;
          id: string;
          kyc_tier: number | null;
          logo_url: string | null;
          owner_user_id: string;
          preferred_badge: boolean;
          slug: string;
          status: string;
          updated_at: string;
        };
        Insert: {
          caps_snapshot?: Json;
          created_at?: string;
          description?: string | null;
          display_name: string;
          id?: string;
          kyc_tier?: number | null;
          logo_url?: string | null;
          owner_user_id: string;
          preferred_badge?: boolean;
          slug: string;
          status?: string;
          updated_at?: string;
        };
        Update: {
          caps_snapshot?: Json;
          created_at?: string;
          description?: string | null;
          display_name?: string;
          id?: string;
          kyc_tier?: number | null;
          logo_url?: string | null;
          owner_user_id?: string;
          preferred_badge?: boolean;
          slug?: string;
          status?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "vendors_owner_user_id_fkey";
            columns: ["owner_user_id"];
            isOneToOne: false;
            referencedRelation: "profiles";
            referencedColumns: ["id"];
          },
        ];
      };
      commission_rates: {
        Row: {
          category_key: string;
          rate_bps: number;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          category_key: string;
          rate_bps: number;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          category_key?: string;
          rate_bps?: number;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      categories: {
        Row: {
          commission_key: string;
          created_at: string;
          id: string;
          name: string;
          parent_id: string | null;
          path: string;
          position: number;
          prohibited: boolean;
          slug: string;
          updated_at: string;
          vat_flag: boolean;
        };
        Insert: {
          commission_key: string;
          created_at?: string;
          id?: string;
          name: string;
          parent_id?: string | null;
          path: string;
          position?: number;
          prohibited?: boolean;
          slug: string;
          updated_at?: string;
          vat_flag?: boolean;
        };
        Update: {
          commission_key?: string;
          created_at?: string;
          id?: string;
          name?: string;
          parent_id?: string | null;
          path?: string;
          position?: number;
          prohibited?: boolean;
          slug?: string;
          updated_at?: string;
          vat_flag?: boolean;
        };
        Relationships: [
          {
            foreignKeyName: "categories_parent_id_fkey";
            columns: ["parent_id"];
            isOneToOne: false;
            referencedRelation: "categories";
            referencedColumns: ["id"];
          },
        ];
      };
      addresses: {
        Row: {
          created_at: string;
          id: string;
          label: string | null;
          landmark: string;
          lat: number | null;
          lng: number | null;
          phone: string | null;
          updated_at: string;
          user_id: string;
        };
        Insert: {
          created_at?: string;
          id?: string;
          label?: string | null;
          landmark: string;
          lat?: number | null;
          lng?: number | null;
          phone?: string | null;
          updated_at?: string;
          user_id: string;
        };
        Update: {
          created_at?: string;
          id?: string;
          label?: string | null;
          landmark?: string;
          lat?: number | null;
          lng?: number | null;
          phone?: string | null;
          updated_at?: string;
          user_id?: string;
        };
        Relationships: [];
      };
      checkout_groups: {
        Row: {
          created_at: string;
          customer_id: string;
          delivery_fee_ngwee: number;
          id: string;
          idempotency_key: string;
          status: string;
          subtotal_ngwee: number;
          total_ngwee: number;
          updated_at: string;
        };
        Insert: {
          created_at?: string;
          customer_id: string;
          delivery_fee_ngwee: number;
          id?: string;
          idempotency_key: string;
          status?: string;
          subtotal_ngwee: number;
          total_ngwee: number;
          updated_at?: string;
        };
        Update: {
          created_at?: string;
          customer_id?: string;
          delivery_fee_ngwee?: number;
          id?: string;
          idempotency_key?: string;
          status?: string;
          subtotal_ngwee?: number;
          total_ngwee?: number;
          updated_at?: string;
        };
        Relationships: [];
      };
      config_audit: {
        Row: {
          id: string;
          actor: string | null;
          table_name: string;
          row_key: string;
          before: Json | null;
          after: Json | null;
          at: string;
        };
        Insert: {
          id?: string;
          actor?: string | null;
          table_name: string;
          row_key: string;
          before?: Json | null;
          after?: Json | null;
          at?: string;
        };
        Update: {
          id?: string;
          actor?: string | null;
          table_name?: string;
          row_key?: string;
          before?: Json | null;
          after?: Json | null;
          at?: string;
        };
        Relationships: [];
      };
      delivery_zones: {
        Row: {
          zone_key: string;
          label: string;
          fee_ngwee: number;
          active: boolean;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          zone_key: string;
          label: string;
          fee_ngwee: number;
          active?: boolean;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          zone_key?: string;
          label?: string;
          fee_ngwee?: number;
          active?: boolean;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      event_instances: {
        Row: {
          capacity: number;
          created_at: string;
          event_id: string;
          id: string;
          starts_at: string;
          updated_at: string;
        };
        Insert: {
          capacity: number;
          created_at?: string;
          event_id: string;
          id?: string;
          starts_at: string;
          updated_at?: string;
        };
        Update: {
          capacity?: number;
          created_at?: string;
          event_id?: string;
          id?: string;
          starts_at?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "event_instances_event_id_fkey";
            columns: ["event_id"];
            isOneToOne: false;
            referencedRelation: "events";
            referencedColumns: ["id"];
          },
        ];
      };
      events: {
        Row: {
          created_at: string;
          description: string | null;
          id: string;
          images: string[];
          lat: number | null;
          lng: number | null;
          organiser_vendor_id: string;
          slug: string;
          status: string;
          title: string;
          updated_at: string;
          venue: string | null;
        };
        Insert: {
          created_at?: string;
          description?: string | null;
          id?: string;
          images?: string[];
          lat?: number | null;
          lng?: number | null;
          organiser_vendor_id: string;
          slug: string;
          status?: string;
          title: string;
          updated_at?: string;
          venue?: string | null;
        };
        Update: {
          created_at?: string;
          description?: string | null;
          id?: string;
          images?: string[];
          lat?: number | null;
          lng?: number | null;
          organiser_vendor_id?: string;
          slug?: string;
          status?: string;
          title?: string;
          updated_at?: string;
          venue?: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "events_organiser_vendor_id_fkey";
            columns: ["organiser_vendor_id"];
            isOneToOne: false;
            referencedRelation: "vendors";
            referencedColumns: ["id"];
          },
        ];
      };
      job_quotes: {
        Row: {
          amount_ngwee: number;
          created_at: string;
          expires_at: string | null;
          id: string;
          job_id: string;
          message: string | null;
          provider_vendor_id: string;
          status: string;
          updated_at: string;
        };
        Insert: {
          amount_ngwee: number;
          created_at?: string;
          expires_at?: string | null;
          id?: string;
          job_id: string;
          message?: string | null;
          provider_vendor_id: string;
          status?: string;
          updated_at?: string;
        };
        Update: {
          amount_ngwee?: number;
          created_at?: string;
          expires_at?: string | null;
          id?: string;
          job_id?: string;
          message?: string | null;
          provider_vendor_id?: string;
          status?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "job_quotes_job_id_fkey";
            columns: ["job_id"];
            isOneToOne: false;
            referencedRelation: "jobs";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "job_quotes_provider_vendor_id_fkey";
            columns: ["provider_vendor_id"];
            isOneToOne: false;
            referencedRelation: "vendors";
            referencedColumns: ["id"];
          },
        ];
      };
      jobs: {
        Row: {
          budget_band_max_ngwee: number | null;
          budget_band_min_ngwee: number | null;
          category: string;
          created_at: string;
          customer_id: string;
          description: string;
          id: string;
          preferred_date: string | null;
          status: string;
          updated_at: string;
        };
        Insert: {
          budget_band_max_ngwee?: number | null;
          budget_band_min_ngwee?: number | null;
          category: string;
          created_at?: string;
          customer_id: string;
          description: string;
          id?: string;
          preferred_date?: string | null;
          status?: string;
          updated_at?: string;
        };
        Update: {
          budget_band_max_ngwee?: number | null;
          budget_band_min_ngwee?: number | null;
          category?: string;
          created_at?: string;
          customer_id?: string;
          description?: string;
          id?: string;
          preferred_date?: string | null;
          status?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      feature_flags: {
        Row: {
          flag: string;
          enabled: boolean;
          description: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          flag: string;
          enabled?: boolean;
          description?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          flag?: string;
          enabled?: boolean;
          description?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      merch_slots: {
        Row: {
          id: string;
          slot_key: string;
          variant_key: string;
          payload: Json;
          schedule_from: string | null;
          schedule_to: string | null;
          position: number;
          active: boolean;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          slot_key: string;
          variant_key: string;
          payload?: Json;
          schedule_from?: string | null;
          schedule_to?: string | null;
          position?: number;
          active?: boolean;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          slot_key?: string;
          variant_key?: string;
          payload?: Json;
          schedule_from?: string | null;
          schedule_to?: string | null;
          position?: number;
          active?: boolean;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      order_events: {
        Row: {
          actor: string | null;
          created_at: string;
          from_status: string | null;
          id: string;
          note: string | null;
          order_id: string;
          to_status: string | null;
        };
        Insert: {
          actor?: string | null;
          created_at?: string;
          from_status?: string | null;
          id?: string;
          note?: string | null;
          order_id: string;
          to_status?: string | null;
        };
        Update: {
          actor?: string | null;
          created_at?: string;
          from_status?: string | null;
          id?: string;
          note?: string | null;
          order_id?: string;
          to_status?: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "order_events_order_id_fkey";
            columns: ["order_id"];
            isOneToOne: false;
            referencedRelation: "orders";
            referencedColumns: ["id"];
          },
        ];
      };
      order_item_products: {
        Row: {
          listing_id: string;
          order_item_id: string;
          product_id: string | null;
        };
        Insert: {
          listing_id: string;
          order_item_id: string;
          product_id?: string | null;
        };
        Update: {
          listing_id?: string;
          order_item_id?: string;
          product_id?: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "order_item_products_listing_id_fkey";
            columns: ["listing_id"];
            isOneToOne: false;
            referencedRelation: "vendor_listings";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "order_item_products_order_item_id_fkey";
            columns: ["order_item_id"];
            isOneToOne: true;
            referencedRelation: "order_items";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "order_item_products_product_id_fkey";
            columns: ["product_id"];
            isOneToOne: false;
            referencedRelation: "products";
            referencedColumns: ["id"];
          },
        ];
      };
      order_item_services: {
        Row: {
          job_id: string | null;
          order_item_id: string;
          quote_id: string | null;
        };
        Insert: {
          job_id?: string | null;
          order_item_id: string;
          quote_id?: string | null;
        };
        Update: {
          job_id?: string | null;
          order_item_id?: string;
          quote_id?: string | null;
        };
        Relationships: [
          {
            foreignKeyName: "order_item_services_job_id_fkey";
            columns: ["job_id"];
            isOneToOne: false;
            referencedRelation: "jobs";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "order_item_services_order_item_id_fkey";
            columns: ["order_item_id"];
            isOneToOne: true;
            referencedRelation: "order_items";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "order_item_services_quote_id_fkey";
            columns: ["quote_id"];
            isOneToOne: false;
            referencedRelation: "job_quotes";
            referencedColumns: ["id"];
          },
        ];
      };
      order_item_tickets: {
        Row: {
          instance_id: string;
          order_item_id: string;
          ticket_type_id: string;
        };
        Insert: {
          instance_id: string;
          order_item_id: string;
          ticket_type_id: string;
        };
        Update: {
          instance_id?: string;
          order_item_id?: string;
          ticket_type_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "order_item_tickets_instance_id_fkey";
            columns: ["instance_id"];
            isOneToOne: false;
            referencedRelation: "event_instances";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "order_item_tickets_order_item_id_fkey";
            columns: ["order_item_id"];
            isOneToOne: true;
            referencedRelation: "order_items";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "order_item_tickets_ticket_type_id_fkey";
            columns: ["ticket_type_id"];
            isOneToOne: false;
            referencedRelation: "ticket_types";
            referencedColumns: ["id"];
          },
        ];
      };
      order_items: {
        Row: {
          created_at: string;
          id: string;
          item_kind: string;
          order_id: string;
          qty: number;
          title_snapshot: string | null;
          unit_price_ngwee: number;
          updated_at: string;
        };
        Insert: {
          created_at?: string;
          id?: string;
          item_kind: string;
          order_id: string;
          qty: number;
          title_snapshot?: string | null;
          unit_price_ngwee: number;
          updated_at?: string;
        };
        Update: {
          created_at?: string;
          id?: string;
          item_kind?: string;
          order_id?: string;
          qty?: number;
          title_snapshot?: string | null;
          unit_price_ngwee?: number;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "order_items_order_id_fkey";
            columns: ["order_id"];
            isOneToOne: false;
            referencedRelation: "orders";
            referencedColumns: ["id"];
          },
        ];
      };
      orders: {
        Row: {
          address_id: string | null;
          checkout_group_id: string;
          cod: boolean;
          commission_snapshot: Json;
          created_at: string;
          customer_id: string;
          delivery_fee_ngwee: number;
          delivery_zone: string | null;
          fulfilment: string;
          id: string;
          status: string;
          updated_at: string;
          vendor_id: string;
        };
        Insert: {
          address_id?: string | null;
          checkout_group_id: string;
          cod?: boolean;
          commission_snapshot?: Json;
          created_at?: string;
          customer_id: string;
          delivery_fee_ngwee?: number;
          delivery_zone?: string | null;
          fulfilment: string;
          id?: string;
          status?: string;
          updated_at?: string;
          vendor_id: string;
        };
        Update: {
          address_id?: string | null;
          checkout_group_id?: string;
          cod?: boolean;
          commission_snapshot?: Json;
          created_at?: string;
          customer_id?: string;
          delivery_fee_ngwee?: number;
          delivery_zone?: string | null;
          fulfilment?: string;
          id?: string;
          status?: string;
          updated_at?: string;
          vendor_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "orders_address_id_fkey";
            columns: ["address_id"];
            isOneToOne: false;
            referencedRelation: "addresses";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "orders_checkout_group_id_fkey";
            columns: ["checkout_group_id"];
            isOneToOne: false;
            referencedRelation: "checkout_groups";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "orders_vendor_id_fkey";
            columns: ["vendor_id"];
            isOneToOne: false;
            referencedRelation: "vendors";
            referencedColumns: ["id"];
          },
        ];
      };
      platform_config: {
        Row: {
          key: string;
          value: Json;
          description: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          key: string;
          value: Json;
          description?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          key?: string;
          value?: Json;
          description?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      prohibited_categories: {
        Row: {
          key: string;
          reason: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          key: string;
          reason: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          key?: string;
          reason?: string;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      products: {
        Row: {
          aliases: string[];
          brand: string | null;
          category_id: string;
          created_at: string;
          id: string;
          merged_into_id: string | null;
          name: string;
          slug: string;
          spec: Json;
          status: string;
          updated_at: string;
        };
        Insert: {
          aliases?: string[];
          brand?: string | null;
          category_id: string;
          created_at?: string;
          id?: string;
          merged_into_id?: string | null;
          name: string;
          slug: string;
          spec?: Json;
          status?: string;
          updated_at?: string;
        };
        Update: {
          aliases?: string[];
          brand?: string | null;
          category_id?: string;
          created_at?: string;
          id?: string;
          merged_into_id?: string | null;
          name?: string;
          slug?: string;
          spec?: Json;
          status?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "products_category_id_fkey";
            columns: ["category_id"];
            isOneToOne: false;
            referencedRelation: "categories";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "products_merged_into_id_fkey";
            columns: ["merged_into_id"];
            isOneToOne: false;
            referencedRelation: "products";
            referencedColumns: ["id"];
          },
        ];
      };
      services: {
        Row: {
          category: string;
          created_at: string;
          description: string | null;
          from_price_ngwee: number | null;
          id: string;
          portfolio_images: string[];
          service_area: string | null;
          status: string;
          title: string;
          updated_at: string;
          vendor_id: string;
        };
        Insert: {
          category: string;
          created_at?: string;
          description?: string | null;
          from_price_ngwee?: number | null;
          id?: string;
          portfolio_images?: string[];
          service_area?: string | null;
          status?: string;
          title: string;
          updated_at?: string;
          vendor_id: string;
        };
        Update: {
          category?: string;
          created_at?: string;
          description?: string | null;
          from_price_ngwee?: number | null;
          id?: string;
          portfolio_images?: string[];
          service_area?: string | null;
          status?: string;
          title?: string;
          updated_at?: string;
          vendor_id?: string;
        };
        Relationships: [
          {
            foreignKeyName: "services_vendor_id_fkey";
            columns: ["vendor_id"];
            isOneToOne: false;
            referencedRelation: "vendors";
            referencedColumns: ["id"];
          },
        ];
      };
      stock_reservations: {
        Row: {
          checkout_group_id: string;
          created_at: string;
          expires_at: string;
          id: string;
          listing_id: string;
          qty: number;
          updated_at: string;
        };
        Insert: {
          checkout_group_id: string;
          created_at?: string;
          expires_at: string;
          id?: string;
          listing_id: string;
          qty: number;
          updated_at?: string;
        };
        Update: {
          checkout_group_id?: string;
          created_at?: string;
          expires_at?: string;
          id?: string;
          listing_id?: string;
          qty?: number;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "stock_reservations_checkout_group_id_fkey";
            columns: ["checkout_group_id"];
            isOneToOne: false;
            referencedRelation: "checkout_groups";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "stock_reservations_listing_id_fkey";
            columns: ["listing_id"];
            isOneToOne: false;
            referencedRelation: "vendor_listings";
            referencedColumns: ["id"];
          },
        ];
      };
      ticket_types: {
        Row: {
          created_at: string;
          event_id: string;
          id: string;
          kind: string;
          name: string;
          price_ngwee: number;
          qty_cap: number | null;
          updated_at: string;
        };
        Insert: {
          created_at?: string;
          event_id: string;
          id?: string;
          kind: string;
          name: string;
          price_ngwee: number;
          qty_cap?: number | null;
          updated_at?: string;
        };
        Update: {
          created_at?: string;
          event_id?: string;
          id?: string;
          kind?: string;
          name?: string;
          price_ngwee?: number;
          qty_cap?: number | null;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "ticket_types_event_id_fkey";
            columns: ["event_id"];
            isOneToOne: false;
            referencedRelation: "events";
            referencedColumns: ["id"];
          },
        ];
      };
      tickets: {
        Row: {
          checked_in_at: string | null;
          created_at: string;
          holder_user_id: string;
          id: string;
          instance_id: string;
          order_item_id: string | null;
          pin_hash: string | null;
          qr_secret: string | null;
          status: string;
          ticket_type_id: string;
          updated_at: string;
        };
        Insert: {
          checked_in_at?: string | null;
          created_at?: string;
          holder_user_id: string;
          id?: string;
          instance_id: string;
          order_item_id?: string | null;
          pin_hash?: string | null;
          qr_secret?: string | null;
          status?: string;
          ticket_type_id: string;
          updated_at?: string;
        };
        Update: {
          checked_in_at?: string | null;
          created_at?: string;
          holder_user_id?: string;
          id?: string;
          instance_id?: string;
          order_item_id?: string | null;
          pin_hash?: string | null;
          qr_secret?: string | null;
          status?: string;
          ticket_type_id?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "tickets_instance_id_fkey";
            columns: ["instance_id"];
            isOneToOne: false;
            referencedRelation: "event_instances";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "tickets_order_item_id_fkey";
            columns: ["order_item_id"];
            isOneToOne: false;
            referencedRelation: "order_items";
            referencedColumns: ["id"];
          },
          {
            foreignKeyName: "tickets_ticket_type_id_fkey";
            columns: ["ticket_type_id"];
            isOneToOne: false;
            referencedRelation: "ticket_types";
            referencedColumns: ["id"];
          },
        ];
      };
      vendor_quotas: {
        Row: {
          tier: number;
          max_listings: number;
          first_orders_cap_ngwee: number | null;
          first_orders_count: number | null;
          payout_velocity: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          tier: number;
          max_listings: number;
          first_orders_cap_ngwee?: number | null;
          first_orders_count?: number | null;
          payout_velocity?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          tier?: number;
          max_listings?: number;
          first_orders_cap_ngwee?: number | null;
          first_orders_count?: number | null;
          payout_velocity?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      audit_log: {
        Row: {
          id: string;
          actor: string | null;
          action: string;
          entity_type: string;
          entity_id: string | null;
          before: Json | null;
          after: Json | null;
          at: string;
        };
        Insert: {
          id?: string;
          actor?: string | null;
          action: string;
          entity_type: string;
          entity_id?: string | null;
          before?: Json | null;
          after?: Json | null;
          at?: string;
        };
        Update: {
          id?: string;
          actor?: string | null;
          action?: string;
          entity_type?: string;
          entity_id?: string | null;
          before?: Json | null;
          after?: Json | null;
          at?: string;
        };
        Relationships: [];
      };
      disputes: {
        Row: {
          id: string;
          order_id: string;
          opener_user_id: string;
          evidence_paths: string[];
          vendor_response: string | null;
          admin_decision: string | null;
          status: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          order_id: string;
          opener_user_id: string;
          evidence_paths?: string[];
          vendor_response?: string | null;
          admin_decision?: string | null;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          order_id?: string;
          opener_user_id?: string;
          evidence_paths?: string[];
          vendor_response?: string | null;
          admin_decision?: string | null;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "disputes_order_id_fkey";
            columns: ["order_id"];
            isOneToOne: false;
            referencedRelation: "orders";
            referencedColumns: ["id"];
          },
        ];
      };
      flags: {
        Row: {
          id: string;
          entity_type: string;
          entity_id: string;
          reason: string;
          reporter_user_id: string;
          status: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          entity_type: string;
          entity_id: string;
          reason: string;
          reporter_user_id: string;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          entity_type?: string;
          entity_id?: string;
          reason?: string;
          reporter_user_id?: string;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      notification_outbox: {
        Row: {
          id: string;
          dedupe_key: string;
          channel: string;
          template: string | null;
          payload: Json;
          status: string;
          attempts: number;
          next_retry_at: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          dedupe_key: string;
          channel: string;
          template?: string | null;
          payload?: Json;
          status?: string;
          attempts?: number;
          next_retry_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          dedupe_key?: string;
          channel?: string;
          template?: string | null;
          payload?: Json;
          status?: string;
          attempts?: number;
          next_retry_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [];
      };
      returns: {
        Row: {
          id: string;
          order_item_id: string;
          lane: number;
          evidence_paths: string[];
          fee_breakdown: Json;
          status: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          order_item_id: string;
          lane: number;
          evidence_paths?: string[];
          fee_breakdown?: Json;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          order_item_id?: string;
          lane?: number;
          evidence_paths?: string[];
          fee_breakdown?: Json;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "returns_order_item_id_fkey";
            columns: ["order_item_id"];
            isOneToOne: false;
            referencedRelation: "order_items";
            referencedColumns: ["id"];
          },
        ];
      };
      reviews: {
        Row: {
          id: string;
          order_item_id: string;
          rating: number;
          body: string | null;
          photos: string[];
          vendor_reply: string | null;
          vendor_reply_at: string | null;
          status: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          order_item_id: string;
          rating: number;
          body?: string | null;
          photos?: string[];
          vendor_reply?: string | null;
          vendor_reply_at?: string | null;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          order_item_id?: string;
          rating?: number;
          body?: string | null;
          photos?: string[];
          vendor_reply?: string | null;
          vendor_reply_at?: string | null;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Relationships: [
          {
            foreignKeyName: "reviews_order_item_id_fkey";
            columns: ["order_item_id"];
            isOneToOne: true;
            referencedRelation: "order_items";
            referencedColumns: ["id"];
          },
        ];
      };
    };
    Views: {
      [_ in never]: never;
    };
    Functions: {
      has_role: { Args: { required_role: string }; Returns: boolean };
      is_valid_price_tiers: { Args: { tiers: Json }; Returns: boolean };
      show_limit: { Args: never; Returns: number };
      show_trgm: { Args: { "": string }; Returns: string[] };
    };
    Enums: {
      [_ in never]: never;
    };
    CompositeTypes: {
      [_ in never]: never;
    };
  };
};

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">;

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">];

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R;
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R;
      }
      ? R
      : never
    : never;

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I;
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I;
      }
      ? I
      : never
    : never;

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    keyof DefaultSchema["Tables"] | { schema: keyof DatabaseWithoutInternals },
  TableName extends (DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never) = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U;
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U;
      }
      ? U
      : never
    : never;

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    keyof DefaultSchema["Enums"] | { schema: keyof DatabaseWithoutInternals },
  EnumName extends (DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never) = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never;

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    keyof DefaultSchema["CompositeTypes"] | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends (PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals;
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never) = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals;
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never;

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const;
