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
