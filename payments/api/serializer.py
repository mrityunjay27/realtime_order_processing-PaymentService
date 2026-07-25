from rest_framework import serializers
from payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order_id", "amount", "status", "transaction_reference", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "transaction_reference", "created_at", "updated_at"]
