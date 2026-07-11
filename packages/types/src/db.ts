export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      addresses: {
        Row: {
          created_at: string
          id: string
          label: string | null
          landmark: string
          lat: number | null
          lng: number | null
          phone: string | null
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          label?: string | null
          landmark: string
          lat?: number | null
          lng?: number | null
          phone?: string | null
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          label?: string | null
          landmark?: string
          lat?: number | null
          lng?: number | null
          phone?: string | null
          updated_at?: string
          user_id?: string
        }
        Relationships: []
      }
      ask_cache: {
        Row: {
          answer: Json
          cited_ids: string[]
          created_at: string
          expires_at: string
          normalized_query: string
        }
        Insert: {
          answer: Json
          cited_ids?: string[]
          created_at?: string
          expires_at: string
          normalized_query: string
        }
        Update: {
          answer?: Json
          cited_ids?: string[]
          created_at?: string
          expires_at?: string
          normalized_query?: string
        }
        Relationships: []
      }
      ask_spend_monthly: {
        Row: {
          admin_reset_at: string | null
          created_at: string
          killed_at: string | null
          month_key: string
          total_usd_micros: number
          updated_at: string
        }
        Insert: {
          admin_reset_at?: string | null
          created_at?: string
          killed_at?: string | null
          month_key: string
          total_usd_micros?: number
          updated_at?: string
        }
        Update: {
          admin_reset_at?: string | null
          created_at?: string
          killed_at?: string | null
          month_key?: string
          total_usd_micros?: number
          updated_at?: string
        }
        Relationships: []
      }
      ask_usage: {
        Row: {
          answered_at: string | null
          client_ip: unknown
          created_at: string
          guest_key: string | null
          id: string
          model: string | null
          month_key: string
          question_hash: string | null
          status: string
          tokens: number
          usd_micros: number
          user_id: string | null
        }
        Insert: {
          answered_at?: string | null
          client_ip?: unknown
          created_at?: string
          guest_key?: string | null
          id?: string
          model?: string | null
          month_key: string
          question_hash?: string | null
          status?: string
          tokens?: number
          usd_micros?: number
          user_id?: string | null
        }
        Update: {
          answered_at?: string | null
          client_ip?: unknown
          created_at?: string
          guest_key?: string | null
          id?: string
          model?: string | null
          month_key?: string
          question_hash?: string | null
          status?: string
          tokens?: number
          usd_micros?: number
          user_id?: string | null
        }
        Relationships: []
      }
      audit_log: {
        Row: {
          action: string
          actor: string | null
          after: Json | null
          at: string
          before: Json | null
          entity_id: string | null
          entity_type: string
          id: string
        }
        Insert: {
          action: string
          actor?: string | null
          after?: Json | null
          at?: string
          before?: Json | null
          entity_id?: string | null
          entity_type: string
          id?: string
        }
        Update: {
          action?: string
          actor?: string | null
          after?: Json | null
          at?: string
          before?: Json | null
          entity_id?: string | null
          entity_type?: string
          id?: string
        }
        Relationships: []
      }
      cart_items: {
        Row: {
          cart_id: string
          created_at: string
          id: string
          listing_id: string
          qty: number
          unit_price_ngwee: number
          updated_at: string
          wholesale: boolean
        }
        Insert: {
          cart_id: string
          created_at?: string
          id?: string
          listing_id: string
          qty: number
          unit_price_ngwee: number
          updated_at?: string
          wholesale?: boolean
        }
        Update: {
          cart_id?: string
          created_at?: string
          id?: string
          listing_id?: string
          qty?: number
          unit_price_ngwee?: number
          updated_at?: string
          wholesale?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "cart_items_cart_id_fkey"
            columns: ["cart_id"]
            isOneToOne: false
            referencedRelation: "carts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "cart_items_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "vendor_listings"
            referencedColumns: ["id"]
          },
        ]
      }
      carts: {
        Row: {
          created_at: string
          guest_token: string | null
          id: string
          status: string
          updated_at: string
          user_id: string | null
        }
        Insert: {
          created_at?: string
          guest_token?: string | null
          id?: string
          status?: string
          updated_at?: string
          user_id?: string | null
        }
        Update: {
          created_at?: string
          guest_token?: string | null
          id?: string
          status?: string
          updated_at?: string
          user_id?: string | null
        }
        Relationships: []
      }
      categories: {
        Row: {
          commission_key: string
          created_at: string
          id: string
          name: string
          parent_id: string | null
          path: string
          position: number
          prohibited: boolean
          slug: string
          updated_at: string
          vat_flag: boolean
        }
        Insert: {
          commission_key: string
          created_at?: string
          id?: string
          name: string
          parent_id?: string | null
          path: string
          position?: number
          prohibited?: boolean
          slug: string
          updated_at?: string
          vat_flag?: boolean
        }
        Update: {
          commission_key?: string
          created_at?: string
          id?: string
          name?: string
          parent_id?: string | null
          path?: string
          position?: number
          prohibited?: boolean
          slug?: string
          updated_at?: string
          vat_flag?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "categories_parent_id_fkey"
            columns: ["parent_id"]
            isOneToOne: false
            referencedRelation: "categories"
            referencedColumns: ["id"]
          },
        ]
      }
      checkout_groups: {
        Row: {
          created_at: string
          customer_id: string
          delivery_fee_ngwee: number
          id: string
          idempotency_key: string
          status: string
          subtotal_ngwee: number
          total_ngwee: number
          updated_at: string
        }
        Insert: {
          created_at?: string
          customer_id: string
          delivery_fee_ngwee: number
          id?: string
          idempotency_key: string
          status?: string
          subtotal_ngwee: number
          total_ngwee: number
          updated_at?: string
        }
        Update: {
          created_at?: string
          customer_id?: string
          delivery_fee_ngwee?: number
          id?: string
          idempotency_key?: string
          status?: string
          subtotal_ngwee?: number
          total_ngwee?: number
          updated_at?: string
        }
        Relationships: []
      }
      commission_rates: {
        Row: {
          category_key: string
          created_at: string
          rate_bps: number
          updated_at: string
        }
        Insert: {
          category_key: string
          created_at?: string
          rate_bps: number
          updated_at?: string
        }
        Update: {
          category_key?: string
          created_at?: string
          rate_bps?: number
          updated_at?: string
        }
        Relationships: []
      }
      config_audit: {
        Row: {
          actor: string | null
          after: Json | null
          at: string
          before: Json | null
          id: string
          row_key: string
          table_name: string
        }
        Insert: {
          actor?: string | null
          after?: Json | null
          at?: string
          before?: Json | null
          id?: string
          row_key: string
          table_name: string
        }
        Update: {
          actor?: string | null
          after?: Json | null
          at?: string
          before?: Json | null
          id?: string
          row_key?: string
          table_name?: string
        }
        Relationships: []
      }
      delivery_zones: {
        Row: {
          active: boolean
          created_at: string
          fee_ngwee: number
          label: string
          updated_at: string
          zone_key: string
        }
        Insert: {
          active?: boolean
          created_at?: string
          fee_ngwee: number
          label: string
          updated_at?: string
          zone_key: string
        }
        Update: {
          active?: boolean
          created_at?: string
          fee_ngwee?: number
          label?: string
          updated_at?: string
          zone_key?: string
        }
        Relationships: []
      }
      disputes: {
        Row: {
          admin_decision: string | null
          created_at: string
          evidence_paths: string[]
          id: string
          opener_user_id: string
          order_id: string
          status: string
          updated_at: string
          vendor_response: string | null
        }
        Insert: {
          admin_decision?: string | null
          created_at?: string
          evidence_paths?: string[]
          id?: string
          opener_user_id: string
          order_id: string
          status?: string
          updated_at?: string
          vendor_response?: string | null
        }
        Update: {
          admin_decision?: string | null
          created_at?: string
          evidence_paths?: string[]
          id?: string
          opener_user_id?: string
          order_id?: string
          status?: string
          updated_at?: string
          vendor_response?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "disputes_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
        ]
      }
      embedding_jobs: {
        Row: {
          attempts: number
          batch_cost_usd: number | null
          created_at: string
          entity_id: string
          entity_kind: string
          id: string
          last_error: string | null
          processed_at: string | null
          search_document_id: string
          status: string
          updated_at: string
        }
        Insert: {
          attempts?: number
          batch_cost_usd?: number | null
          created_at?: string
          entity_id: string
          entity_kind: string
          id?: string
          last_error?: string | null
          processed_at?: string | null
          search_document_id: string
          status?: string
          updated_at?: string
        }
        Update: {
          attempts?: number
          batch_cost_usd?: number | null
          created_at?: string
          entity_id?: string
          entity_kind?: string
          id?: string
          last_error?: string | null
          processed_at?: string | null
          search_document_id?: string
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "embedding_jobs_search_document_id_fkey"
            columns: ["search_document_id"]
            isOneToOne: false
            referencedRelation: "search_documents"
            referencedColumns: ["id"]
          },
        ]
      }
      event_instances: {
        Row: {
          capacity: number
          created_at: string
          event_id: string
          id: string
          starts_at: string
          updated_at: string
        }
        Insert: {
          capacity: number
          created_at?: string
          event_id: string
          id?: string
          starts_at: string
          updated_at?: string
        }
        Update: {
          capacity?: number
          created_at?: string
          event_id?: string
          id?: string
          starts_at?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "event_instances_event_id_fkey"
            columns: ["event_id"]
            isOneToOne: false
            referencedRelation: "events"
            referencedColumns: ["id"]
          },
        ]
      }
      events: {
        Row: {
          created_at: string
          description: string | null
          id: string
          images: string[]
          lat: number | null
          lng: number | null
          organiser_vendor_id: string
          slug: string
          status: string
          title: string
          updated_at: string
          venue: string | null
        }
        Insert: {
          created_at?: string
          description?: string | null
          id?: string
          images?: string[]
          lat?: number | null
          lng?: number | null
          organiser_vendor_id: string
          slug: string
          status?: string
          title: string
          updated_at?: string
          venue?: string | null
        }
        Update: {
          created_at?: string
          description?: string | null
          id?: string
          images?: string[]
          lat?: number | null
          lng?: number | null
          organiser_vendor_id?: string
          slug?: string
          status?: string
          title?: string
          updated_at?: string
          venue?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "events_organiser_vendor_id_fkey"
            columns: ["organiser_vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      feature_flags: {
        Row: {
          created_at: string
          description: string | null
          enabled: boolean
          flag: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          description?: string | null
          enabled?: boolean
          flag: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          description?: string | null
          enabled?: boolean
          flag?: string
          updated_at?: string
        }
        Relationships: []
      }
      flags: {
        Row: {
          created_at: string
          entity_id: string
          entity_type: string
          id: string
          reason: string
          reporter_user_id: string
          status: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          entity_id: string
          entity_type: string
          id?: string
          reason: string
          reporter_user_id: string
          status?: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          entity_id?: string
          entity_type?: string
          id?: string
          reason?: string
          reporter_user_id?: string
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      funnel_events: {
        Row: {
          checkout_group_id: string | null
          created_at: string
          customer_id: string | null
          id: string
          snapshot: Json
          stage: string
        }
        Insert: {
          checkout_group_id?: string | null
          created_at?: string
          customer_id?: string | null
          id?: string
          snapshot?: Json
          stage: string
        }
        Update: {
          checkout_group_id?: string | null
          created_at?: string
          customer_id?: string | null
          id?: string
          snapshot?: Json
          stage?: string
        }
        Relationships: [
          {
            foreignKeyName: "funnel_events_checkout_group_id_fkey"
            columns: ["checkout_group_id"]
            isOneToOne: false
            referencedRelation: "checkout_groups"
            referencedColumns: ["id"]
          },
        ]
      }
      invoice_counters: {
        Row: {
          next_no: number
          series: string
        }
        Insert: {
          next_no?: number
          series: string
        }
        Update: {
          next_no?: number
          series?: string
        }
        Relationships: []
      }
      invoices: {
        Row: {
          created_at: string
          id: string
          no: number
          order_id: string
          series: string
          snapshot: Json
          vat_flag: boolean
          vat_ngwee: number
        }
        Insert: {
          created_at?: string
          id?: string
          no: number
          order_id: string
          series: string
          snapshot?: Json
          vat_flag?: boolean
          vat_ngwee?: number
        }
        Update: {
          created_at?: string
          id?: string
          no?: number
          order_id?: string
          series?: string
          snapshot?: Json
          vat_flag?: boolean
          vat_ngwee?: number
        }
        Relationships: [
          {
            foreignKeyName: "invoices_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
        ]
      }
      job_quotes: {
        Row: {
          amount_ngwee: number
          created_at: string
          expires_at: string | null
          id: string
          job_id: string
          message: string | null
          provider_vendor_id: string
          status: string
          updated_at: string
        }
        Insert: {
          amount_ngwee: number
          created_at?: string
          expires_at?: string | null
          id?: string
          job_id: string
          message?: string | null
          provider_vendor_id: string
          status?: string
          updated_at?: string
        }
        Update: {
          amount_ngwee?: number
          created_at?: string
          expires_at?: string | null
          id?: string
          job_id?: string
          message?: string | null
          provider_vendor_id?: string
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "job_quotes_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "jobs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "job_quotes_provider_vendor_id_fkey"
            columns: ["provider_vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      jobs: {
        Row: {
          budget_band_max_ngwee: number | null
          budget_band_min_ngwee: number | null
          category: string
          created_at: string
          customer_id: string
          description: string
          id: string
          preferred_date: string | null
          status: string
          updated_at: string
        }
        Insert: {
          budget_band_max_ngwee?: number | null
          budget_band_min_ngwee?: number | null
          category: string
          created_at?: string
          customer_id: string
          description: string
          id?: string
          preferred_date?: string | null
          status?: string
          updated_at?: string
        }
        Update: {
          budget_band_max_ngwee?: number | null
          budget_band_min_ngwee?: number | null
          category?: string
          created_at?: string
          customer_id?: string
          description?: string
          id?: string
          preferred_date?: string | null
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      kyc_records: {
        Row: {
          created_at: string
          doc_storage_paths: string[]
          id: string
          momo_name_match: Json | null
          reviewer_notes: string | null
          status: string
          tier: number
          updated_at: string
          vendor_id: string
        }
        Insert: {
          created_at?: string
          doc_storage_paths?: string[]
          id?: string
          momo_name_match?: Json | null
          reviewer_notes?: string | null
          status?: string
          tier: number
          updated_at?: string
          vendor_id: string
        }
        Update: {
          created_at?: string
          doc_storage_paths?: string[]
          id?: string
          momo_name_match?: Json | null
          reviewer_notes?: string | null
          status?: string
          tier?: number
          updated_at?: string
          vendor_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "kyc_records_vendor_id_fkey"
            columns: ["vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      ledger_accounts: {
        Row: {
          created_at: string
          id: string
          kind: string
          updated_at: string
          vendor_id: string | null
        }
        Insert: {
          created_at?: string
          id?: string
          kind: string
          updated_at?: string
          vendor_id?: string | null
        }
        Update: {
          created_at?: string
          id?: string
          kind?: string
          updated_at?: string
          vendor_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "ledger_accounts_vendor_id_fkey"
            columns: ["vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      ledger_postings: {
        Row: {
          account_id: string
          amount_ngwee: number
          created_at: string
          id: string
          transaction_id: string
        }
        Insert: {
          account_id: string
          amount_ngwee: number
          created_at?: string
          id?: string
          transaction_id: string
        }
        Update: {
          account_id?: string
          amount_ngwee?: number
          created_at?: string
          id?: string
          transaction_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "ledger_postings_account_id_fkey"
            columns: ["account_id"]
            isOneToOne: false
            referencedRelation: "ledger_accounts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "ledger_postings_transaction_id_fkey"
            columns: ["transaction_id"]
            isOneToOne: false
            referencedRelation: "ledger_transactions"
            referencedColumns: ["id"]
          },
        ]
      }
      ledger_transactions: {
        Row: {
          checkout_group_id: string | null
          created_at: string
          id: string
          idempotency_key: string | null
          kind: string
          order_id: string | null
          payment_id: string | null
          payout_id: string | null
          refund_id: string | null
        }
        Insert: {
          checkout_group_id?: string | null
          created_at?: string
          id?: string
          idempotency_key?: string | null
          kind: string
          order_id?: string | null
          payment_id?: string | null
          payout_id?: string | null
          refund_id?: string | null
        }
        Update: {
          checkout_group_id?: string | null
          created_at?: string
          id?: string
          idempotency_key?: string | null
          kind?: string
          order_id?: string | null
          payment_id?: string | null
          payout_id?: string | null
          refund_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "ledger_transactions_checkout_group_id_fkey"
            columns: ["checkout_group_id"]
            isOneToOne: false
            referencedRelation: "checkout_groups"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "ledger_transactions_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "ledger_transactions_payment_id_fkey"
            columns: ["payment_id"]
            isOneToOne: false
            referencedRelation: "payments"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "ledger_transactions_payout_id_fkey"
            columns: ["payout_id"]
            isOneToOne: false
            referencedRelation: "payouts"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "ledger_transactions_refund_id_fkey"
            columns: ["refund_id"]
            isOneToOne: false
            referencedRelation: "refunds"
            referencedColumns: ["id"]
          },
        ]
      }
      listing_images: {
        Row: {
          cloudinary_public_id: string
          created_at: string
          id: string
          listing_id: string
          position: number
          updated_at: string
        }
        Insert: {
          cloudinary_public_id: string
          created_at?: string
          id?: string
          listing_id: string
          position: number
          updated_at?: string
        }
        Update: {
          cloudinary_public_id?: string
          created_at?: string
          id?: string
          listing_id?: string
          position?: number
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "listing_images_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "vendor_listings"
            referencedColumns: ["id"]
          },
        ]
      }
      merch_slots: {
        Row: {
          active: boolean
          created_at: string
          id: string
          payload: Json
          position: number
          schedule_from: string | null
          schedule_to: string | null
          slot_key: string
          updated_at: string
          variant_key: string
        }
        Insert: {
          active?: boolean
          created_at?: string
          id?: string
          payload?: Json
          position?: number
          schedule_from?: string | null
          schedule_to?: string | null
          slot_key: string
          updated_at?: string
          variant_key: string
        }
        Update: {
          active?: boolean
          created_at?: string
          id?: string
          payload?: Json
          position?: number
          schedule_from?: string | null
          schedule_to?: string | null
          slot_key?: string
          updated_at?: string
          variant_key?: string
        }
        Relationships: []
      }
      notification_outbox: {
        Row: {
          attempts: number
          channel: string
          created_at: string
          dedupe_key: string
          id: string
          next_retry_at: string | null
          payload: Json
          status: string
          template: string | null
          updated_at: string
        }
        Insert: {
          attempts?: number
          channel: string
          created_at?: string
          dedupe_key: string
          id?: string
          next_retry_at?: string | null
          payload?: Json
          status?: string
          template?: string | null
          updated_at?: string
        }
        Update: {
          attempts?: number
          channel?: string
          created_at?: string
          dedupe_key?: string
          id?: string
          next_retry_at?: string | null
          payload?: Json
          status?: string
          template?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      order_events: {
        Row: {
          actor: string | null
          created_at: string
          from_status: string | null
          id: string
          note: string | null
          order_id: string
          to_status: string | null
        }
        Insert: {
          actor?: string | null
          created_at?: string
          from_status?: string | null
          id?: string
          note?: string | null
          order_id: string
          to_status?: string | null
        }
        Update: {
          actor?: string | null
          created_at?: string
          from_status?: string | null
          id?: string
          note?: string | null
          order_id?: string
          to_status?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "order_events_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
        ]
      }
      order_item_products: {
        Row: {
          listing_id: string
          order_item_id: string
          product_id: string | null
        }
        Insert: {
          listing_id: string
          order_item_id: string
          product_id?: string | null
        }
        Update: {
          listing_id?: string
          order_item_id?: string
          product_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "order_item_products_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "vendor_listings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_item_products_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: true
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_item_products_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
        ]
      }
      order_item_services: {
        Row: {
          job_id: string | null
          order_item_id: string
          quote_id: string | null
        }
        Insert: {
          job_id?: string | null
          order_item_id: string
          quote_id?: string | null
        }
        Update: {
          job_id?: string | null
          order_item_id?: string
          quote_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "order_item_services_job_id_fkey"
            columns: ["job_id"]
            isOneToOne: false
            referencedRelation: "jobs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_item_services_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: true
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_item_services_quote_id_fkey"
            columns: ["quote_id"]
            isOneToOne: false
            referencedRelation: "job_quotes"
            referencedColumns: ["id"]
          },
        ]
      }
      order_item_tickets: {
        Row: {
          instance_id: string
          order_item_id: string
          ticket_type_id: string
        }
        Insert: {
          instance_id: string
          order_item_id: string
          ticket_type_id: string
        }
        Update: {
          instance_id?: string
          order_item_id?: string
          ticket_type_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "order_item_tickets_instance_id_fkey"
            columns: ["instance_id"]
            isOneToOne: false
            referencedRelation: "event_instances"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_item_tickets_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: true
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_item_tickets_ticket_type_id_fkey"
            columns: ["ticket_type_id"]
            isOneToOne: false
            referencedRelation: "ticket_types"
            referencedColumns: ["id"]
          },
        ]
      }
      order_items: {
        Row: {
          created_at: string
          id: string
          item_kind: string
          order_id: string
          qty: number
          title_snapshot: string | null
          unit_price_ngwee: number
          updated_at: string
        }
        Insert: {
          created_at?: string
          id?: string
          item_kind: string
          order_id: string
          qty: number
          title_snapshot?: string | null
          unit_price_ngwee: number
          updated_at?: string
        }
        Update: {
          created_at?: string
          id?: string
          item_kind?: string
          order_id?: string
          qty?: number
          title_snapshot?: string | null
          unit_price_ngwee?: number
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "order_items_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
        ]
      }
      orders: {
        Row: {
          address_id: string | null
          checkout_group_id: string
          cod: boolean
          commission_snapshot: Json
          created_at: string
          customer_id: string
          delivery_fee_ngwee: number
          delivery_zone: string | null
          fulfilment: string
          id: string
          pickup_collected_at: string | null
          pickup_pin_hash: string | null
          pickup_qr_secret: string | null
          pickup_token_version: number
          status: string
          updated_at: string
          vendor_id: string
        }
        Insert: {
          address_id?: string | null
          checkout_group_id: string
          cod?: boolean
          commission_snapshot?: Json
          created_at?: string
          customer_id: string
          delivery_fee_ngwee?: number
          delivery_zone?: string | null
          fulfilment: string
          id?: string
          pickup_collected_at?: string | null
          pickup_pin_hash?: string | null
          pickup_qr_secret?: string | null
          pickup_token_version?: number
          status?: string
          updated_at?: string
          vendor_id: string
        }
        Update: {
          address_id?: string | null
          checkout_group_id?: string
          cod?: boolean
          commission_snapshot?: Json
          created_at?: string
          customer_id?: string
          delivery_fee_ngwee?: number
          delivery_zone?: string | null
          fulfilment?: string
          id?: string
          pickup_collected_at?: string | null
          pickup_pin_hash?: string | null
          pickup_qr_secret?: string | null
          pickup_token_version?: number
          status?: string
          updated_at?: string
          vendor_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "orders_address_id_fkey"
            columns: ["address_id"]
            isOneToOne: false
            referencedRelation: "addresses"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "orders_checkout_group_id_fkey"
            columns: ["checkout_group_id"]
            isOneToOne: false
            referencedRelation: "checkout_groups"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "orders_vendor_id_fkey"
            columns: ["vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      payments: {
        Row: {
          amount_ngwee: number
          checkout_group_id: string
          created_at: string
          id: string
          lenco_reference: string
          provider: string
          rail: string
          raw: Json
          status: string
          updated_at: string
        }
        Insert: {
          amount_ngwee: number
          checkout_group_id: string
          created_at?: string
          id?: string
          lenco_reference: string
          provider: string
          rail: string
          raw?: Json
          status?: string
          updated_at?: string
        }
        Update: {
          amount_ngwee?: number
          checkout_group_id?: string
          created_at?: string
          id?: string
          lenco_reference?: string
          provider?: string
          rail?: string
          raw?: Json
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "payments_checkout_group_id_fkey"
            columns: ["checkout_group_id"]
            isOneToOne: false
            referencedRelation: "checkout_groups"
            referencedColumns: ["id"]
          },
        ]
      }
      payouts: {
        Row: {
          amount_ngwee: number
          created_at: string
          id: string
          lenco_reference: string
          rail: string
          resolve_snapshot: Json
          status: string
          updated_at: string
          vendor_id: string
        }
        Insert: {
          amount_ngwee: number
          created_at?: string
          id?: string
          lenco_reference: string
          rail: string
          resolve_snapshot?: Json
          status?: string
          updated_at?: string
          vendor_id: string
        }
        Update: {
          amount_ngwee?: number
          created_at?: string
          id?: string
          lenco_reference?: string
          rail?: string
          resolve_snapshot?: Json
          status?: string
          updated_at?: string
          vendor_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "payouts_vendor_id_fkey"
            columns: ["vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      platform_config: {
        Row: {
          created_at: string
          description: string | null
          key: string
          updated_at: string
          value: Json
        }
        Insert: {
          created_at?: string
          description?: string | null
          key: string
          updated_at?: string
          value: Json
        }
        Update: {
          created_at?: string
          description?: string | null
          key?: string
          updated_at?: string
          value?: Json
        }
        Relationships: []
      }
      products: {
        Row: {
          aliases: string[]
          brand: string | null
          category_id: string
          created_at: string
          id: string
          merged_into_id: string | null
          name: string
          slug: string
          spec: Json
          status: string
          updated_at: string
        }
        Insert: {
          aliases?: string[]
          brand?: string | null
          category_id: string
          created_at?: string
          id?: string
          merged_into_id?: string | null
          name: string
          slug: string
          spec?: Json
          status?: string
          updated_at?: string
        }
        Update: {
          aliases?: string[]
          brand?: string | null
          category_id?: string
          created_at?: string
          id?: string
          merged_into_id?: string | null
          name?: string
          slug?: string
          spec?: Json
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "products_category_id_fkey"
            columns: ["category_id"]
            isOneToOne: false
            referencedRelation: "categories"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "products_merged_into_id_fkey"
            columns: ["merged_into_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          created_at: string
          deleted_at: string | null
          display_name: string | null
          dpa_consent_at: string | null
          id: string
          locale: string
          notif_prefs: Json
          phone: string | null
          updated_at: string
        }
        Insert: {
          created_at?: string
          deleted_at?: string | null
          display_name?: string | null
          dpa_consent_at?: string | null
          id: string
          locale?: string
          notif_prefs?: Json
          phone?: string | null
          updated_at?: string
        }
        Update: {
          created_at?: string
          deleted_at?: string | null
          display_name?: string | null
          dpa_consent_at?: string | null
          id?: string
          locale?: string
          notif_prefs?: Json
          phone?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      prohibited_categories: {
        Row: {
          created_at: string
          key: string
          reason: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          key: string
          reason: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          key?: string
          reason?: string
          updated_at?: string
        }
        Relationships: []
      }
      rate_counters: {
        Row: {
          count: number
          expires_at: string
          id: string
          key: string
          scope: string
          window_start: string
        }
        Insert: {
          count?: number
          expires_at: string
          id?: string
          key: string
          scope: string
          window_start: string
        }
        Update: {
          count?: number
          expires_at?: string
          id?: string
          key?: string
          scope?: string
          window_start?: string
        }
        Relationships: []
      }
      reconciliation_reports: {
        Row: {
          created_at: string
          discrepancies: Json
          id: string
          report_date: string
          summary: Json
        }
        Insert: {
          created_at?: string
          discrepancies?: Json
          id?: string
          report_date: string
          summary?: Json
        }
        Update: {
          created_at?: string
          discrepancies?: Json
          id?: string
          report_date?: string
          summary?: Json
        }
        Relationships: []
      }
      refunds: {
        Row: {
          amount_ngwee: number
          breakdown: Json
          created_at: string
          id: string
          lane: number
          order_id: string
          payout_ref: string | null
          status: string
          updated_at: string
        }
        Insert: {
          amount_ngwee: number
          breakdown?: Json
          created_at?: string
          id?: string
          lane: number
          order_id: string
          payout_ref?: string | null
          status?: string
          updated_at?: string
        }
        Update: {
          amount_ngwee?: number
          breakdown?: Json
          created_at?: string
          id?: string
          lane?: number
          order_id?: string
          payout_ref?: string | null
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "refunds_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "refunds_payout_ref_fkey"
            columns: ["payout_ref"]
            isOneToOne: false
            referencedRelation: "payouts"
            referencedColumns: ["id"]
          },
        ]
      }
      returns: {
        Row: {
          created_at: string
          evidence_paths: string[]
          fee_breakdown: Json
          id: string
          lane: number
          order_item_id: string
          status: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          evidence_paths?: string[]
          fee_breakdown?: Json
          id?: string
          lane: number
          order_item_id: string
          status?: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          evidence_paths?: string[]
          fee_breakdown?: Json
          id?: string
          lane?: number
          order_item_id?: string
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "returns_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: false
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
        ]
      }
      reviews: {
        Row: {
          body: string | null
          created_at: string
          id: string
          order_item_id: string
          photos: string[]
          rating: number
          status: string
          updated_at: string
          vendor_reply: string | null
          vendor_reply_at: string | null
        }
        Insert: {
          body?: string | null
          created_at?: string
          id?: string
          order_item_id: string
          photos?: string[]
          rating: number
          status?: string
          updated_at?: string
          vendor_reply?: string | null
          vendor_reply_at?: string | null
        }
        Update: {
          body?: string | null
          created_at?: string
          id?: string
          order_item_id?: string
          photos?: string[]
          rating?: number
          status?: string
          updated_at?: string
          vendor_reply?: string | null
          vendor_reply_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "reviews_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: true
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
        ]
      }
      search_documents: {
        Row: {
          body: string
          boost_signals: Json
          category_path: string | null
          created_at: string
          embedding: string | null
          entity_id: string
          entity_kind: string
          id: string
          is_public: boolean
          lat: number | null
          lng: number | null
          locale_terms: string[] | null
          price_max_ngwee: number | null
          price_min_ngwee: number | null
          title: string
          tsv: unknown
          updated_at: string
        }
        Insert: {
          body?: string
          boost_signals?: Json
          category_path?: string | null
          created_at?: string
          embedding?: string | null
          entity_id: string
          entity_kind: string
          id?: string
          is_public?: boolean
          lat?: number | null
          lng?: number | null
          locale_terms?: string[] | null
          price_max_ngwee?: number | null
          price_min_ngwee?: number | null
          title?: string
          tsv?: unknown
          updated_at?: string
        }
        Update: {
          body?: string
          boost_signals?: Json
          category_path?: string | null
          created_at?: string
          embedding?: string | null
          entity_id?: string
          entity_kind?: string
          id?: string
          is_public?: boolean
          lat?: number | null
          lng?: number | null
          locale_terms?: string[] | null
          price_max_ngwee?: number | null
          price_min_ngwee?: number | null
          title?: string
          tsv?: unknown
          updated_at?: string
        }
        Relationships: []
      }
      services: {
        Row: {
          category: string
          created_at: string
          description: string | null
          from_price_ngwee: number | null
          id: string
          portfolio_images: string[]
          service_area: string | null
          status: string
          title: string
          updated_at: string
          vendor_id: string
        }
        Insert: {
          category: string
          created_at?: string
          description?: string | null
          from_price_ngwee?: number | null
          id?: string
          portfolio_images?: string[]
          service_area?: string | null
          status?: string
          title: string
          updated_at?: string
          vendor_id: string
        }
        Update: {
          category?: string
          created_at?: string
          description?: string | null
          from_price_ngwee?: number | null
          id?: string
          portfolio_images?: string[]
          service_area?: string | null
          status?: string
          title?: string
          updated_at?: string
          vendor_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "services_vendor_id_fkey"
            columns: ["vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      stock_reservations: {
        Row: {
          checkout_group_id: string
          created_at: string
          expires_at: string
          id: string
          listing_id: string
          qty: number
          updated_at: string
        }
        Insert: {
          checkout_group_id: string
          created_at?: string
          expires_at: string
          id?: string
          listing_id: string
          qty: number
          updated_at?: string
        }
        Update: {
          checkout_group_id?: string
          created_at?: string
          expires_at?: string
          id?: string
          listing_id?: string
          qty?: number
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "stock_reservations_checkout_group_id_fkey"
            columns: ["checkout_group_id"]
            isOneToOne: false
            referencedRelation: "checkout_groups"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "stock_reservations_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "vendor_listings"
            referencedColumns: ["id"]
          },
        ]
      }
      synonyms: {
        Row: {
          canonical: string
          created_at: string
          id: string
          term: string
        }
        Insert: {
          canonical: string
          created_at?: string
          id?: string
          term: string
        }
        Update: {
          canonical?: string
          created_at?: string
          id?: string
          term?: string
        }
        Relationships: []
      }
      ticket_transfers: {
        Row: {
          cancelled_at: string | null
          claimed_at: string | null
          claimed_by_user_id: string | null
          created_at: string
          expires_at: string
          from_user_id: string
          id: string
          status: string
          ticket_id: string
          to_phone: string
          updated_at: string
        }
        Insert: {
          cancelled_at?: string | null
          claimed_at?: string | null
          claimed_by_user_id?: string | null
          created_at?: string
          expires_at: string
          from_user_id: string
          id?: string
          status?: string
          ticket_id: string
          to_phone: string
          updated_at?: string
        }
        Update: {
          cancelled_at?: string | null
          claimed_at?: string | null
          claimed_by_user_id?: string | null
          created_at?: string
          expires_at?: string
          from_user_id?: string
          id?: string
          status?: string
          ticket_id?: string
          to_phone?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "ticket_transfers_ticket_id_fkey"
            columns: ["ticket_id"]
            isOneToOne: false
            referencedRelation: "tickets"
            referencedColumns: ["id"]
          },
        ]
      }
      ticket_types: {
        Row: {
          created_at: string
          event_id: string
          id: string
          kind: string
          name: string
          per_customer_cap: number | null
          price_ngwee: number
          qty_cap: number | null
          updated_at: string
        }
        Insert: {
          created_at?: string
          event_id: string
          id?: string
          kind: string
          name: string
          per_customer_cap?: number | null
          price_ngwee: number
          qty_cap?: number | null
          updated_at?: string
        }
        Update: {
          created_at?: string
          event_id?: string
          id?: string
          kind?: string
          name?: string
          per_customer_cap?: number | null
          price_ngwee?: number
          qty_cap?: number | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "ticket_types_event_id_fkey"
            columns: ["event_id"]
            isOneToOne: false
            referencedRelation: "events"
            referencedColumns: ["id"]
          },
        ]
      }
      tickets: {
        Row: {
          checked_in_at: string | null
          created_at: string
          holder_user_id: string
          id: string
          instance_id: string
          order_item_id: string | null
          pin_hash: string | null
          qr_secret: string | null
          status: string
          ticket_type_id: string
          updated_at: string
        }
        Insert: {
          checked_in_at?: string | null
          created_at?: string
          holder_user_id: string
          id?: string
          instance_id: string
          order_item_id?: string | null
          pin_hash?: string | null
          qr_secret?: string | null
          status?: string
          ticket_type_id: string
          updated_at?: string
        }
        Update: {
          checked_in_at?: string | null
          created_at?: string
          holder_user_id?: string
          id?: string
          instance_id?: string
          order_item_id?: string | null
          pin_hash?: string | null
          qr_secret?: string | null
          status?: string
          ticket_type_id?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "tickets_instance_id_fkey"
            columns: ["instance_id"]
            isOneToOne: false
            referencedRelation: "event_instances"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "tickets_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: false
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "tickets_ticket_type_id_fkey"
            columns: ["ticket_type_id"]
            isOneToOne: false
            referencedRelation: "ticket_types"
            referencedColumns: ["id"]
          },
        ]
      }
      user_roles: {
        Row: {
          created_at: string
          id: string
          role: string
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id?: string
          role: string
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          role?: string
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_roles_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      vendor_listings: {
        Row: {
          condition: string
          created_at: string
          id: string
          moq: number
          price_ngwee: number
          price_tiers: Json | null
          product_id: string | null
          return_window_hours: number | null
          returnable: boolean
          sku: string | null
          status: string
          stock_mode: string
          stock_qty: number | null
          title_override: string | null
          updated_at: string
          vendor_id: string
          wholesale: boolean
        }
        Insert: {
          condition: string
          created_at?: string
          id?: string
          moq?: number
          price_ngwee: number
          price_tiers?: Json | null
          product_id?: string | null
          return_window_hours?: number | null
          returnable?: boolean
          sku?: string | null
          status?: string
          stock_mode: string
          stock_qty?: number | null
          title_override?: string | null
          updated_at?: string
          vendor_id: string
          wholesale?: boolean
        }
        Update: {
          condition?: string
          created_at?: string
          id?: string
          moq?: number
          price_ngwee?: number
          price_tiers?: Json | null
          product_id?: string | null
          return_window_hours?: number | null
          returnable?: boolean
          sku?: string | null
          status?: string
          stock_mode?: string
          stock_qty?: number | null
          title_override?: string | null
          updated_at?: string
          vendor_id?: string
          wholesale?: boolean
        }
        Relationships: [
          {
            foreignKeyName: "vendor_listings_product_id_fkey"
            columns: ["product_id"]
            isOneToOne: false
            referencedRelation: "products"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "vendor_listings_vendor_id_fkey"
            columns: ["vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      vendor_locations: {
        Row: {
          created_at: string
          hours: Json
          id: string
          landmark: string
          lat: number
          lng: number
          updated_at: string
          vendor_id: string
        }
        Insert: {
          created_at?: string
          hours?: Json
          id?: string
          landmark: string
          lat: number
          lng: number
          updated_at?: string
          vendor_id: string
        }
        Update: {
          created_at?: string
          hours?: Json
          id?: string
          landmark?: string
          lat?: number
          lng?: number
          updated_at?: string
          vendor_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "vendor_locations_vendor_id_fkey"
            columns: ["vendor_id"]
            isOneToOne: false
            referencedRelation: "vendors"
            referencedColumns: ["id"]
          },
        ]
      }
      vendor_quotas: {
        Row: {
          created_at: string
          first_orders_cap_ngwee: number | null
          first_orders_count: number | null
          max_listings: number
          payout_velocity: Json
          tier: number
          updated_at: string
        }
        Insert: {
          created_at?: string
          first_orders_cap_ngwee?: number | null
          first_orders_count?: number | null
          max_listings: number
          payout_velocity?: Json
          tier: number
          updated_at?: string
        }
        Update: {
          created_at?: string
          first_orders_cap_ngwee?: number | null
          first_orders_count?: number | null
          max_listings?: number
          payout_velocity?: Json
          tier?: number
          updated_at?: string
        }
        Relationships: []
      }
      vendors: {
        Row: {
          caps_snapshot: Json
          created_at: string
          description: string | null
          display_name: string
          id: string
          kyc_tier: number | null
          logo_url: string | null
          owner_user_id: string
          payout_hold_until: string | null
          payout_msisdn: string | null
          payout_rail: string | null
          preferred_badge: boolean
          slug: string
          status: string
          updated_at: string
        }
        Insert: {
          caps_snapshot?: Json
          created_at?: string
          description?: string | null
          display_name: string
          id?: string
          kyc_tier?: number | null
          logo_url?: string | null
          owner_user_id: string
          payout_hold_until?: string | null
          payout_msisdn?: string | null
          payout_rail?: string | null
          preferred_badge?: boolean
          slug: string
          status?: string
          updated_at?: string
        }
        Update: {
          caps_snapshot?: Json
          created_at?: string
          description?: string | null
          display_name?: string
          id?: string
          kyc_tier?: number | null
          logo_url?: string | null
          owner_user_id?: string
          payout_hold_until?: string | null
          payout_msisdn?: string | null
          payout_rail?: string | null
          preferred_badge?: boolean
          slug?: string
          status?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "vendors_owner_user_id_fkey"
            columns: ["owner_user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      webhook_events: {
        Row: {
          created_at: string
          event_id: string
          id: string
          processed_at: string | null
          provider: string
          raw: Json
          signature_valid: boolean
        }
        Insert: {
          created_at?: string
          event_id: string
          id?: string
          processed_at?: string | null
          provider: string
          raw?: Json
          signature_valid?: boolean
        }
        Update: {
          created_at?: string
          event_id?: string
          id?: string
          processed_at?: string | null
          provider?: string
          raw?: Json
          signature_valid?: boolean
        }
        Relationships: []
      }
    }
    Views: {
      ask_usage_monthly: {
        Row: {
          answered_count: number | null
          month_key: string | null
          total_tokens: number | null
          total_usd_micros: number | null
        }
        Relationships: []
      }
    }
    Functions: {
      ask_current_month_key: { Args: never; Returns: string }
      ask_monthly_cap_usd_micros: { Args: never; Returns: number }
      ask_read_config_int: {
        Args: { p_default: number; p_key: string }
        Returns: number
      }
      bump_rate_counter: {
        Args: {
          p_key: string
          p_limit: number
          p_scope: string
          p_window: string
        }
        Returns: {
          allowed: boolean
          retry_after_seconds: number
        }[]
      }
      cart_guest_token: { Args: never; Returns: string }
      claim_embedding_jobs: {
        Args: { p_limit: number }
        Returns: {
          body: string
          entity_id: string
          entity_kind: string
          job_id: string
          locale_terms: string[]
          search_document_id: string
          title: string
        }[]
      }
      cleanup_expired_rate_counters: { Args: never; Returns: number }
      embedding_enqueue_document: {
        Args: {
          p_entity_id: string
          p_entity_kind: string
          p_search_document_id: string
        }
        Returns: undefined
      }
      expand_search_terms: { Args: { p_query: string }; Returns: string }
      finalize_ask_answer: {
        Args: {
          p_model: string
          p_reservation_id: string
          p_tokens: number
          p_usd_micros: number
        }
        Returns: {
          killed: boolean
          month_total_usd_micros: number
          success: boolean
        }[]
      }
      has_role: { Args: { required_role: string }; Returns: boolean }
      is_valid_price_tiers: { Args: { tiers: Json }; Returns: boolean }
      next_invoice_no: { Args: { p_series: string }; Returns: number }
      reserve_ask_quota: {
        Args: {
          p_client_ip: unknown
          p_guest_key: string
          p_question_hash: string
          p_user_id: string
        }
        Returns: {
          allowed: boolean
          reason: string
          reservation_id: string
        }[]
      }
      reset_ask_kill_switch: {
        Args: { p_month_key?: string }
        Returns: boolean
      }
      search_apply_boost: {
        Args: { p_base_score: number; p_boost_signals: Json }
        Returns: number
      }
      search_cascade_vendor_children: {
        Args: { p_vendor_id: string }
        Returns: undefined
      }
      search_document_tsv: {
        Args: { p_body: string; p_locale_terms: string[]; p_title: string }
        Returns: unknown
      }
      search_mark_unpublished: {
        Args: { p_entity_id: string; p_entity_kind: string }
        Returns: undefined
      }
      search_remove_document: {
        Args: { p_entity_id: string; p_entity_kind: string }
        Returns: undefined
      }
      search_rrf: {
        Args: { filters?: Json; query: string; query_embedding?: string }
        Returns: {
          body: string
          boost_signals: Json
          category_path: string
          entity_id: string
          entity_kind: string
          id: string
          lat: number
          lng: number
          locale_terms: string[]
          price_max_ngwee: number
          price_min_ngwee: number
          rrf_score: number
          title: string
        }[]
      }
      search_upsert_event: { Args: { p_event_id: string }; Returns: undefined }
      search_upsert_listing: {
        Args: { p_listing_id: string }
        Returns: undefined
      }
      search_upsert_product: {
        Args: { p_product_id: string }
        Returns: undefined
      }
      search_upsert_service: {
        Args: { p_service_id: string }
        Returns: undefined
      }
      search_upsert_vendor: {
        Args: { p_vendor_id: string }
        Returns: undefined
      }
      show_limit: { Args: never; Returns: number }
      show_trgm: { Args: { "": string }; Returns: string[] }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const

